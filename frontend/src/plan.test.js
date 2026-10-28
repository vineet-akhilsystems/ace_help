import {describe,it,expect} from 'vitest';
import {total,validation,tagTask,taskIssues,adjustLongDay,snapOption,ticketlessRows,applyTicketLinks,ideaNotes,markDone,completionIssues,aceTask,groupIssues} from './plan';
describe('editable preview validation',()=>{
  const tasks=[{description:'Work',start:'09:45',end:'14:30'},{description:'More work',start:'14:30',end:'19:00'}];
  it('computes the displayed total',()=>expect(total(tasks)).toBe('09:15'));
  it('accepts a valid contiguous day',()=>expect(validation([{date:'2026-09-23',tasks}])).toEqual([]));
  it('blocks gaps',()=>expect(validation([{date:'2026-09-23',tasks:[tasks[0],{...tasks[1],start:'14:31'}]}])).toHaveLength(1));
  it('blocks empty descriptions and invalid end times',()=>expect(validation([{date:'2026-09-23',tasks:[{description:'',start:'09:45',end:'20:00'}]}]).length).toBeGreaterThan(1));
  it('removes ticket prefixes together with the suggestion',()=>expect(tagTask({description:'[ASPL-169999] Fixed issue.',ticket:'ASPL-169999'},'')).toMatchObject({description:'Fixed issue.',ticket:null}));
  it('reserves description room for ticket prefix',()=>expect(tagTask({description:'x'.repeat(500)},'ASPL-169999').description.length).toBe(500));
  it('blocks a selected ticket when its prefix was removed',()=>expect(validation([{date:'2026-09-23',tasks:[{description:'Unprefixed',ticket:'ASPL-169999',start:'09:45',end:'19:00'}]}])).toHaveLength(1));
  it('accepts a 9-hour day and rejects 9:30',()=>{
    expect(validation([{date:'2026-09-23',tasks:[{description:'Work',start:'09:45',end:'18:45'}]}])).toEqual([]);
    expect(validation([{date:'2026-09-23',tasks:[{description:'Work',start:'09:45',end:'19:15'}]}])).toHaveLength(1);
  });
  it('adjusts an existing 9:30 plan without changing earlier rows',()=>{
    const old={date:'2026-09-15',totalHours:'09:30',tasks:[
      {description:'First',start:'09:45',end:'14:30'},
      {description:'Last',start:'14:30',end:'19:15'}]};
    const fixed=adjustLongDay(old);
    expect(fixed.tasks[0]).toEqual(old.tasks[0]);
    expect(fixed.tasks[1].end).toBe('19:00');
    expect(fixed.totalHours).toBe('09:15');
    expect(validation([fixed])).toEqual([]);
  });
});

it('task drafts need every required ACE field and exact options', () => {
  const options = {taskType:['Bug'], priority:['High'], client:['Aster RV Hospital'], module:['EMR'], frdNature:['Low'], status:['Open']};
  const good = {taskType:'Bug', priority:'High', client:'Aster RV Hospital', module:'EMR', frdNature:'', status:'Open',
    targetDate:'2030-10-01T18:00', effortDays:1, keyword:'vitals', description:'d', clientRemarks:'c', employeeRemarks:'e'};
  expect(taskIssues([good], options)).toEqual([]);
  expect(taskIssues([{...good, client:'Aster RV'}], options)).toEqual(['Task 1: Client Name "Aster RV" is not an ACE option.']);
  expect(taskIssues([{...good, module:'', effortDays:0}], options)).toHaveLength(2);
  expect(taskIssues([], options)).toEqual(['Add at least one task.']);
});

it('matches ACE options that differ only in spacing or case', () => {
  const options = {taskType:['Bug'], priority:['High'], client:['Cloud LIS '], module:['Reports - Lab '], frdNature:['Low'], status:['Open']};
  expect(snapOption('cloud  lis', options.client)).toBe('Cloud LIS ');
  expect(snapOption('Cloud', options.client)).toBe('Cloud');
  const good = {taskType:'Bug', priority:'High', client:'Cloud LIS', module:'Reports - Lab', frdNature:'', status:'Open',
    targetDate:'2030-10-01T18:00', effortDays:1, keyword:'k', description:'d', clientRemarks:'c', employeeRemarks:'e'};
  expect(taskIssues([good], options)).toEqual([]);
  expect(taskIssues(Array(31).fill(good), options)[0]).toMatch(/at most 30/);
});
describe('tickets for untagged timesheet rows',()=>{
  const plan={date:'2026-10-27',tasks:[
    {description:'[ASPL-170001] Tagged work',ticket:'ASPL-170001',start:'09:45',end:'12:00'},
    {description:'Untagged work on reports',ticket:null,start:'12:00',end:'14:30'}]};
  it('lists only rows without a ticket, with their minutes',()=>
    expect(ticketlessRows([plan])).toEqual([{date:'2026-10-27',tasks:[{index:1,description:'Untagged work on reports',minutes:150}]}]));
  it('skips days where every row has a ticket',()=>
    expect(ticketlessRows([{...plan,tasks:[plan.tasks[0]]}])).toEqual([]));
  it('tags linked rows and leaves already-tagged rows alone',()=>{
    const {plans,applied}=applyTicketLinks([plan],[{date:'2026-10-27',index:1,ticket:'ASPL-170009'},
      {date:'2026-10-27',index:0,ticket:'ASPL-170010'},{date:'2026-10-28',index:0,ticket:'ASPL-170011'}]);
    expect(applied).toBe(1);
    expect(plans[0].tasks[1]).toMatchObject({ticket:'ASPL-170009',description:'[ASPL-170009] Untagged work on reports'});
    expect(plans[0].tasks[0].ticket).toBe('ASPL-170001');
  });
});
describe('tickets from ticket ideas',()=>{
  const item=(kind,title,repo='emr')=>({date:'2026-10-28',kind,title,repo,evidence:[]});
  it('condenses selected items per day and project',()=>{
    const notes=ideaNotes([item('commit','Fix vitals'),item('file changed','File changed: vitals.py'),
      item('file changed','File changed: chart.jsx'),item('folder','Folder created: reports','billing')],'Met Satyendra sir');
    const lines=notes.split('\n');
    expect(lines[1]).toBe('2026-10-28 · emr: commit: "Fix vitals"; file changed: vitals.py, chart.jsx.');
    expect(lines[2]).toBe('2026-10-28 · billing: folder: reports.');
    expect(lines[3]).toBe('Met Satyendra sir');
  });
  it('keeps select-all within the notes limit',()=>{
    const many=Array.from({length:3000},(_, i)=>item('file changed',`File changed: f${i}.py`,`repo${i%400}`));
    expect(ideaNotes(many).length).toBeLessThanOrEqual(20000);
    const oneRepo=Array.from({length:20},(_, i)=>item('file changed',`File changed: g${i}.py`));
    expect(ideaNotes(oneRepo)).toContain('g11.py (+8 more)');
  });
  it('sets the ACE status from the completed answer and blocks fill until answered',()=>{
    const statuses=['Open','Working','Completed'];
    expect(markDone({status:'Open',targetDate:'2026-10-29T18:00'},true,statuses)).toEqual({status:'Completed',done:true,targetDate:'2026-10-29T18:00'});
    expect(markDone({status:'Completed'},false,statuses)).toEqual({status:'Open',done:false});
    expect(completionIssues([{askDone:true,done:null},{askDone:true,done:false},{}])).toEqual(['Task 1: answer "Have you completed this?"']);
  });
});
describe('selected tickets',()=>{
  it('numbers problems by the ticket position, not the selection position',()=>
    expect(taskIssues([{}],null,[3])[0]).toBe('Task 3: choose Task Type.'));
  it('sends only ACE fields',()=>
    expect(aceTask({keyword:'k',effortDays:'1.5',pick:true,existingTicket:null,outcome:{},link:{},askDone:true,done:true,linkedTicket:'x',workDate:'2026-10-21',warnings:['w']}))
      .toEqual({keyword:'k',effortDays:1.5,warnings:[]}));
});
describe('review problems',()=>{
  it('groups the same problem across tickets into ranges',()=>
    expect(groupIssues(['Task 1: choose Client Name.','Task 2: choose Client Name.','Task 3: choose Client Name.',
      'Task 5: choose Client Name.','Task 2: set Target Date.','Tick at least one ticket to create.']))
      .toEqual(['Tick at least one ticket to create.','Tasks 1–3, 5: choose Client Name.','Task 2: set Target Date.']));
});
describe('target date',()=>{
  it('flags a Target Date before now, because ACE replaces it',()=>{
    const t={taskType:'Bug',priority:'High',client:'C',module:'M',status:'Open',targetDate:'2026-10-21T18:00',effortDays:1,
      keyword:'k',description:'d',clientRemarks:'.',employeeRemarks:'.'};
    expect(taskIssues([t],null,[1],new Date(2026,9,28,23,0))).toEqual(['Task 1: Target Date must be later than now (ACE replaces a past date).']);
    expect(taskIssues([{...t,targetDate:'2026-10-29T18:00'}],null,[1],new Date(2026,9,28,23,0))).toEqual([]);
  });
});
