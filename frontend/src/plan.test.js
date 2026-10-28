import {describe,it,expect} from 'vitest';
import {total,validation,tagTask,taskIssues,adjustLongDay,snapOption} from './plan';
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
    targetDate:'2026-10-01T18:00', effortDays:1, keyword:'vitals', description:'d', clientRemarks:'c', employeeRemarks:'e'};
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
    targetDate:'2026-10-01T18:00', effortDays:1, keyword:'k', description:'d', clientRemarks:'c', employeeRemarks:'e'};
  expect(taskIssues([good], options)).toEqual([]);
  expect(taskIssues(Array(31).fill(good), options)[0]).toMatch(/at most 30/);
});
