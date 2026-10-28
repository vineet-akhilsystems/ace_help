import {describe, expect, test} from 'vitest';
import {agentPayload, mergeIncomingDraft, newDrafts} from './agent';

const base = {date:'2026-10-26', toDate:'2026-10-28', notes:'met Yash', perDay:{'2026-10-27':'demo'}, agent:'claude'};

describe('agentPayload', () => {
  test('single day sends shared notes and no end date', () => {
    expect(agentPayload({...base, range:false, perDayMode:false}))
      .toEqual({fromDate:'2026-10-26', toDate:null, agent:'claude', notes:'met Yash', perDay:{}});
  });
  test('per-day range sends per-day notes only', () => {
    expect(agentPayload({...base, range:true, perDayMode:true}))
      .toEqual({fromDate:'2026-10-26', toDate:'2026-10-28', agent:'claude', notes:'', perDay:{'2026-10-27':'demo'}});
  });
});

describe('newDrafts', () => {
  test('ignores drafts already seen', () => {
    const list = [{date:'2026-10-26', createdAt:'2026-10-27T10:00:00Z', tasks:3},
                  {date:'2026-10-24', createdAt:'2026-10-27T09:00:00Z', tasks:2}];
    expect(newDrafts(list, {'2026-10-24':'2026-10-27T09:00:00Z'}).map(d => d.date)).toEqual(['2026-10-26']);
  });
});

describe('mergeIncomingDraft', () => {
  const plan = {date:'2026-10-26', tasks:[{description:'mine'}]};
  const draft = {date:'2026-10-26', tasks:[{description:'agent'}]};
  test('mergeIncomingDraft keeps edited plan', () => {
    const plans = [plan];
    const result = mergeIncomingDraft(plans, draft, true);
    expect(result.plans).toBe(plans);
    expect(result.notice).toBe('A new draft from your agent for 2026-10-26 is ready. Load it?');
  });
  test('mergeIncomingDraft replaces unedited plan', () => {
    expect(mergeIncomingDraft([plan], draft, false)).toEqual({plans:[draft], notice:null});
  });
  test('mergeIncomingDraft appends a new date in date order', () => {
    const other = {date:'2026-10-24', tasks:[]};
    expect(mergeIncomingDraft([plan], other, true).plans.map(p => p.date)).toEqual(['2026-10-24', '2026-10-26']);
  });
});

test('single-day run keeps typed notes even if per-day mode was left on', () => {
  expect(agentPayload({...base, range:false, perDayMode:true}).notes).toBe('met Yash');
});
