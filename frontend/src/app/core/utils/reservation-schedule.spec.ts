import {
  isReservationDateAllowed,
  reservationTimeSlots,
  reservationTimestamp,
  upcomingReservationDays,
} from './reservation-schedule';

describe('reservation schedule CU17', () => {
  const now = new Date('2026-09-12T14:10:00Z'); // 10:10 en Bolivia

  it('generates exactly the next seven local calendar days', () => {
    const days = upcomingReservationDays(now);
    expect(days).toHaveLength(7);
    expect(days.map((day) => day.value)).toEqual([
      '2026-09-12', '2026-09-13', '2026-09-14', '2026-09-15',
      '2026-09-16', '2026-09-17', '2026-09-18',
    ]);
    expect(days[0]).toEqual(expect.objectContaining({ weekday: 'SÁB', day: '12', month: 'SEP' }));
  });

  it('allows only dates in the seven-day window', () => {
    expect(isReservationDateAllowed('2026-09-12', now)).toBe(true);
    expect(isReservationDateAllowed('2026-09-18', now)).toBe(true);
    expect(isReservationDateAllowed('2026-09-11', now)).toBe(false);
    expect(isReservationDateAllowed('2026-09-19', now)).toBe(false);
  });

  it('creates 30-minute slots that finish before closing', () => {
    expect(reservationTimeSlots('08:00:00', '10:10:00', '2026-09-13', now)).toEqual([
      '08:00', '08:30', '09:00', '09:30',
    ]);
  });

  it('does not show past or current slots for today', () => {
    expect(reservationTimeSlots('08:00:00', '12:00:00', '2026-09-12', now)).toEqual([
      '10:30', '11:00', '11:30',
    ]);
  });

  it('keeps the selected Bolivia wall time in the API timestamp', () => {
    expect(reservationTimestamp('2026-09-13', '16:30')).toBe('2026-09-13T16:30:00-04:00');
  });
});
