import sys
import asyncio
from datetime import timedelta

# Windows: Playwright launches its browser via a subprocess, which requires the
# Proactor event loop. uvicorn may otherwise select the Selector loop, causing
# NotImplementedError on subprocess_exec. Force Proactor before the loop starts.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
import json
import re
from datetime import date, datetime
from pydantic import BaseModel, Field
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from backend.app_session import Session, PortalError
from backend.app_timesheet import Timesheets
from backend.app_status import StatusScanner, month_status, set_leave
from backend.app_tasks import (TaskCreator, TaskDraft, TaskPlanRequest, TicketLinkRequest, TimesheetTicketRequest,
                               check_drafts, load_form, make_task_drafts, match_new_tickets, option_texts,
                               ticket_drafts_for_timesheet)
from backend.config import ROOT, RUNTIME, setting
from backend.app_rules import is_working_day, today_ist, working_dates
from backend.app_models import DayPlan
from backend.services.ticket_ideas import find_ticket_ideas
from backend.services.providers import ProviderError, transcribe
from backend.services import agent_drafts, agent_runner
from backend.services.agent_context import day_context, skip_reason
from backend.services.agent_drafts import AgentDraft, accept_draft
from backend.services.user_tickets import load_user_tickets

session = Session()
portal = Timesheets(session)
creator = TaskCreator(session)
scanner = StatusScanner(session, portal)
planning_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app):
    yield
    await session.close()


app = FastAPI(title='ACE Timesheet Assistant', lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', 'testserver'])
LOCAL_ORIGIN_PATTERN = re.compile(r'^http://(localhost|127\.0\.0\.1)(:\d+)?$')


@app.middleware('http')
async def local_requests(request: Request, call_next):
    origin = request.headers.get('origin')
    if origin and not LOCAL_ORIGIN_PATTERN.match(origin):
        return JSONResponse({'detail': 'Only the local application may access this API.'}, status_code=403)
    if (request.method == 'POST' or request.url.path in ('/tickets', '/task-options', '/status')
            or request.url.path.startswith('/agent/')) and request.headers.get('x-ace-client') != '1':
        return JSONResponse({'detail': 'Missing local application request header.'}, status_code=403)
    if int(request.headers.get('content-length', '0')) > 12 * 1024 * 1024:
        return JSONResponse({'detail': 'Request too large.'}, status_code=413)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.exception_handler(ProviderError)
async def provider_error(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=502)


@app.exception_handler(PortalError)
async def portal_error(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=409)


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=422)


def reject_agent_draft(errors: list[str]) -> None:
    run = agent_drafts.current
    if run:
        run.rejects += 1
        run.last_errors = errors


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    # Invalid shapes never enter agent_submit; they still consume a correction attempt.
    if request.url.path == '/agent/submit':
        reject_agent_draft([f"{'.'.join(map(str, error['loc']))}: {error['msg']}" for error in exc.errors()])
    return await request_validation_exception_handler(request, exc)


@app.get('/health')
async def health():
    return {'status': 'ok', 'today': today_ist().isoformat(), 'saveEnabled': False,
            'providers': {name: bool(setting(name + '_API_KEY')) for name in ('SARVAM',)}}


@app.post('/transcribe')
async def speech(audio: UploadFile = File(...)):
    data = await audio.read(10 * 1024 * 1024 + 1)
    if not data or len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, 'Audio must be nonempty and no larger than 10 MB.')
    if audio.content_type not in ('audio/webm', 'audio/ogg', 'audio/wav', 'audio/mp4', 'audio/mpeg'):
        raise HTTPException(415, 'Unsupported recording format.')
    return {'transcript': await transcribe(data, 'recording.' + {'audio/webm':'webm', 'audio/ogg':'ogg',
        'audio/wav':'wav', 'audio/mp4':'m4a', 'audio/mpeg':'mp3'}[audio.content_type], audio.content_type)}


def optional_tickets():
    tickets = portal.ticket_cache
    if tickets is None:
        portal.load_cached_tickets()
        tickets = portal.ticket_cache
    if not tickets:
        return [], 'Tickets are unavailable, so tasks are untagged. Retry loading tickets in the app to enable matching.'
    return tickets, None


@app.get('/tickets')
async def tickets():
    try:
        return await portal.tickets()
    except PortalError:
        raise
    except Exception:
        import traceback
        traceback.print_exc()
        raise PortalError('Could not load assigned tickets. Check the opened ACE browser or retry, or open the terminal for details.') from None


class TicketIdeaRequest(BaseModel):
    fromDate: date
    toDate: date


@app.post('/ticket-ideas')
async def ticket_ideas(request: TicketIdeaRequest):
    if request.fromDate > request.toDate or request.toDate > today_ist() or request.toDate - request.fromDate > timedelta(days=30):
        raise HTTPException(422, 'Choose up to 31 past or current days in order.')
    return await asyncio.to_thread(find_ticket_ideas, request.fromDate, request.toDate)


@app.post('/validate')
async def validate(plans: list[DayPlan]):
    if not plans or len(plans) > 45 or len({p.date for p in plans}) != len(plans):
        raise HTTPException(422, 'Provide 1–45 plans with unique dates.')
    return {'valid': True}


@app.post('/fill')
async def fill(plans: DayPlan | list[DayPlan]):
    items = plans if isinstance(plans, list) else [plans]
    await validate(items)
    return await portal.fill(items)


def task_options(form):
    return {'options': option_texts(form), 'assignee': creator.assignee, 'loadedAt': form.get('loadedAt')}


@app.get('/task-options')
async def get_task_options():
    return task_options(load_form())


@app.post('/task-options/refresh')
async def refresh_task_options():
    return task_options(await creator.refresh_options())


@app.post('/tasks/plan')
async def plan_tasks(request: TaskPlanRequest):
    async with planning_lock:
        existing = optional_tickets()[0] if request.checkExisting else ()
        return {'tasks': await make_task_drafts(request.transcript, request.defaults, today_ist(),
                                                agent=request.agent, existing=existing)}


@app.post('/tasks/from-timesheet')
async def tasks_from_timesheet(request: TimesheetTicketRequest):
    known = [t.ticket for t in portal.ticket_cache or []]
    return {'tasks': ticket_drafts_for_timesheet(request.days, load_form(), today_ist()), 'known': known}


@app.post('/tasks/link-tickets')
async def link_tickets(request: TicketLinkRequest):
    assigned = await tickets()
    return {'links': match_new_tickets(request.descriptions, assigned, request.known),
            'tickets': [t.model_dump() for t in assigned]}


@app.post('/tasks/fill')
async def fill_tasks(drafts: list[TaskDraft]):
    if not 1 <= len(drafts) <= 30:
        raise HTTPException(422, 'Provide 1–30 tasks.')
    check_drafts(drafts, load_form())
    return await creator.fill(drafts)


@app.post('/tasks/create')
async def create_tasks(drafts: list[TaskDraft]):
    """Fills, checks and saves each reviewed ticket in ACE (tickets only; timesheets are never saved)."""
    if not 1 <= len(drafts) <= 30:
        raise HTTPException(422, 'Provide 1–30 tasks.')
    check_drafts(drafts, load_form())
    known = [t.ticket for t in portal.ticket_cache or []]
    result = await creator.fill(drafts, save=True)
    missing = [r for r in result['tasks'] if r['status'] in ('saved', 'unconfirmed') and not r.get('ticket')]
    if missing:
        # ACE did not show the new number, so find each ticket in the Assigned list by its description.
        try:
            assigned = await tickets()
            links = match_new_tickets([drafts[r['index'] - 1].description for r in missing], assigned, known)
            for r, ticket in zip(missing, links):
                if ticket:
                    r.update(ticket=ticket, status='saved', message=f'Saved in ACE as {ticket}.')
            result['tickets'] = [t.model_dump() for t in assigned]
        except PortalError:
            pass
    return result


MONTH_PATTERN = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')


def check_month(month):
    if not MONTH_PATTERN.match(month or ''):
        raise HTTPException(422, 'Month must look like YYYY-MM.')
    if month > today_ist().strftime('%Y-%m'):
        raise HTTPException(422, 'That month has not started yet.')


class StatusRefresh(BaseModel):
    month: str
    full: bool = False


class LeaveMark(BaseModel):
    day: date
    leave: bool


class DayCheck(BaseModel):
    day: date


@app.get('/status')
async def status(month: str):
    check_month(month)
    return month_status(month, today_ist())


@app.post('/status/check-day')
async def status_check_day(request: DayCheck):
    day = request.day
    if not is_working_day(day) or day > today_ist():
        raise HTTPException(422, 'Only past or current working days can be checked.')
    return await scanner.scan_day(day)


@app.post('/status/leave')
async def status_leave(mark: LeaveMark):
    if not is_working_day(mark.day) or mark.day > today_ist():
        raise HTTPException(422, 'Only past or current working days can be marked as leave.')
    set_leave(mark.day.isoformat(), mark.leave)
    return month_status(mark.day.strftime('%Y-%m'), today_ist())


@app.post('/status/refresh-stream')
async def status_refresh(request: StatusRefresh):
    check_month(request.month)

    async def event_generator():
        queue = asyncio.Queue()

        def on_progress(step, detail=None, icon=None):
            queue.put_nowait({'type': 'step', 'step': step, 'detail': detail, 'icon': icon or 'info',
                              'time': datetime.now().strftime('%H:%M:%S')})

        async def worker():
            try:
                checked = await scanner.scan(request.month, today_ist(), request.full, on_progress)
                queue.put_nowait({'type': 'result', 'checked': checked,
                                  'status': month_status(request.month, today_ist())})
            except Exception as e:
                queue.put_nowait({'type': 'error', 'message': str(e) or 'ACE check failed. See the terminal for details.'})
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(worker())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
        finally:
            await task

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def agent_day_context(day: date) -> dict:
    run = agent_drafts.current
    if run and run.day == day:
        # Context and draft validation share one scan, even for concurrent tool calls.
        with run.context_lock:
            if run.context is None:
                run.context = day_context(day, run.notes, optional_tickets()[0])
            return run.context
    return day_context(day, None, optional_tickets()[0])


def agent_step(message: str) -> None:
    run = agent_drafts.current
    if run:
        run.events.append({'type': 'step', 'step': message[:200], 'detail': None, 'icon': 'ai',
                               'time': datetime.now().strftime('%H:%M:%S')})


@app.get('/agent/context')
async def agent_context(date: date):
    context = await asyncio.to_thread(agent_day_context, date)
    run = agent_drafts.current
    if run and run.day == date:
        run.context_seen = True
    return context


@app.get('/agent/tickets/{aspl}')
async def agent_ticket(aspl: str):
    tickets, _ = await asyncio.to_thread(load_user_tickets, optional_tickets()[0])
    match = next((t for t in tickets if t.ticket == aspl.strip().upper()), None)
    if not match:
        raise HTTPException(404, 'Not one of your tickets.')
    return match


@app.post('/agent/submit')
async def agent_submit(draft: AgentDraft):
    active = agent_drafts.current
    if active and active.day != draft.date:
        error = f'This run is drafting {active.day}; do not submit another date.'
        reject_agent_draft([error])
        raise HTTPException(422, error)
    context = await asyncio.to_thread(agent_day_context, draft.date)
    # Recheck mutable ACE/leave state without repeating the filesystem scan.
    active = agent_drafts.current
    reason = skip_reason(draft.date) if active and active.day == draft.date and active.context is not None else None
    if reason:
        reject_agent_draft([reason])
        raise HTTPException(422, reason)
    tickets, _ = await asyncio.to_thread(load_user_tickets, optional_tickets()[0])
    plan, errors = accept_draft(draft, tickets, context)
    run = agent_drafts.current
    if errors:
        reject_agent_draft(errors)
        agent_step(f'Draft for {draft.date} needs changes: {errors[0]}')
        return JSONResponse({'detail': errors}, status_code=422)
    agent_drafts.store.save(plan)
    if run and run.day == draft.date:
        run.plan = plan
    agent_step(f'Draft for {draft.date} received ({len(plan.tasks)} tasks)')
    return {'plan': plan.model_dump(mode='json')}


class AgentEvent(BaseModel):
    message: str


@app.post('/agent/event')
async def agent_event(event: AgentEvent):
    agent_step(event.message)
    return {'ok': True}


@app.get('/agent/agents')
async def agent_agents():
    return agent_runner.available_agents()


class AgentDraftRequest(BaseModel):
    fromDate: date
    toDate: date | None = None
    agent: str
    notes: str = Field(default='', max_length=20000)
    perDay: dict[date, str] = Field(default_factory=dict)


@app.post('/agent/draft-stream')
async def agent_draft_stream(request: AgentDraftRequest, raw: Request):
    if not any(a['id'] == request.agent and a['installed'] and a['verified'] for a in agent_runner.available_agents()):
        raise HTTPException(422, 'Choose an available agent.')
    end = request.toDate or request.fromDate
    if not 0 <= (end - request.fromDate).days <= 62:
        raise HTTPException(422, 'Date range must be ordered and at most 63 calendar days.')
    dates = working_dates(request.fromDate, end)
    if not dates:
        raise HTTPException(422, 'This range contains no working dates.')
    base_url = f'http://127.0.0.1:{raw.url.port}'

    async def event_generator():
        queue = asyncio.Queue()

        def on_progress(step: str, detail: str | None = None, icon: str | None = None):
            queue.put_nowait({'type': 'step', 'step': step, 'detail': detail, 'icon': icon or 'info',
                              'time': datetime.now().strftime('%H:%M:%S')})

        async def worker():
            try:
                async with planning_lock:
                    plans, no_work, skipped = [], [], []
                    shared = len(dates) > 1 and request.notes.strip()
                    for day in dates:
                        reason = await asyncio.to_thread(skip_reason, day)
                        if reason:
                            skipped.append(reason)
                            on_progress(reason, None, 'check')
                            continue
                        notes = request.perDay.get(day, request.notes).strip()
                        if shared and day not in request.perDay:
                            notes = (f'(These notes cover {dates[0]} to {dates[-1]}; use only items that clearly '
                                     f'belong to {day}.)\n{notes}')
                        plan = await agent_runner.run_for_day(request.agent, day, notes, on_progress, base_url=base_url)
                        if plan and shared and day not in request.perDay:
                            plan.warnings.append('Shared notes repeated for this date. Confirm that every task applies to this day.')
                        if plan:
                            plans.append(plan.model_dump(mode='json'))
                        else:
                            no_work.append(day.isoformat())
                            on_progress(f'No work found for {day.isoformat()}; dictate the day instead.', None, 'info')
                    queue.put_nowait({'type': 'result', 'plans': plans, 'noWork': no_work, 'skipped': skipped})
            except Exception as e:
                queue.put_nowait({'type': 'error', 'message': str(e)})
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(worker())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get('/agent/drafts')
async def agent_drafts_list():
    return agent_drafts.store.list()


@app.get('/agent/drafts/{day}')
async def agent_draft(day: date):
    plan = agent_drafts.store.load(day)
    if not plan:
        raise HTTPException(404, 'No agent draft for that date.')
    return plan


@app.get('/screenshots/{name}')
async def screenshot(name: str):
    if not re.fullmatch(r'(\d{4}-\d{2}-\d{2}|task)-[a-f0-9]{12}\.png', name) or not (RUNTIME / name).is_file():
        raise HTTPException(404)
    return FileResponse(RUNTIME / name)


# Deliberately no /save endpoint, no ticket mutation and no task Save click.
DIST = ROOT / 'frontend' / 'dist'
if DIST.exists():
    app.mount('/', StaticFiles(directory=DIST, html=True), name='frontend')
