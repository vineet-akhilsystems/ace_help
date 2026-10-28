import {describe, expect, it} from 'vitest';
import {leadingBlanks, pendingDays, progress, shiftMonth} from './status';

describe('dashboard status helpers', () => {
  it('lists pending days oldest first', () => {
    const days = [{date:'2026-09-10', status:'partial'}, {date:'2026-09-02', status:'missing'},
      {date:'2026-09-03', status:'filled'}, {date:'2026-09-04', status:'failed'}, {date:'2026-09-05', status:'weekend'}];
    expect(pendingDays(days).map(d => d.date)).toEqual(['2026-09-02', '2026-09-04', '2026-09-10']);
  });

  it('leaves leave days out of progress', () => {
    expect(progress({workingDays:21, counts:{filled:15, leave:1}})).toBe(75);
    expect(progress({workingDays:0, counts:{filled:0, leave:0}})).toBe(0);
  });

  it('moves between months across years', () => {
    expect(shiftMonth('2026-01', -1)).toBe('2025-12');
    expect(shiftMonth('2026-12', 1)).toBe('2027-01');
  });

  it('places the 1st under the right weekday', () => {
    expect(leadingBlanks('2026-09')).toBe(1); // 1 Sep 2026 is a Tuesday
    expect(leadingBlanks('2026-06')).toBe(0); // 1 Jun 2026 is a Monday
  });
});
