export const APP_TIMEZONE = 'America/La_Paz';
export const RESERVATION_WINDOW_DAYS = 7;
export const RESERVATION_SLOT_MINUTES = 30;
export const RESERVATION_TIMEZONE_OFFSET = '-04:00';

export interface ReservationDay {
  value: string;
  weekday: string;
  day: string;
  month: string;
}

function zonedParts(value: Date): Record<string, string> {
  return Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: APP_TIMEZONE,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    })
      .formatToParts(value)
      .map((part) => [part.type, part.value]),
  );
}

export function localDateInBolivia(value = new Date()): string {
  const parts = zonedParts(value);
  return `${parts['year']}-${parts['month']}-${parts['day']}`;
}

export function upcomingReservationDays(now = new Date()): ReservationDay[] {
  const [year, month, day] = localDateInBolivia(now).split('-').map(Number);
  const weekdayFormatter = new Intl.DateTimeFormat('es-BO', {
    weekday: 'short',
    timeZone: 'UTC',
  });
  const monthFormatter = new Intl.DateTimeFormat('es-BO', {
    month: 'short',
    timeZone: 'UTC',
  });
  return Array.from({ length: RESERVATION_WINDOW_DAYS }, (_, index) => {
    const date = new Date(Date.UTC(year, month - 1, day + index, 12));
    const value = date.toISOString().slice(0, 10);
    return {
      value,
      weekday: weekdayFormatter.format(date).replace('.', '').toUpperCase(),
      day: String(date.getUTCDate()).padStart(2, '0'),
      month: monthFormatter.format(date).replace('.', '').slice(0, 3).toUpperCase(),
    };
  });
}

export function isReservationDateAllowed(date: string, now = new Date()): boolean {
  return upcomingReservationDays(now).some((day) => day.value === date);
}

export function minutesOf(value: string): number {
  const [hours, minutes] = value.slice(0, 5).split(':').map(Number);
  return hours * 60 + minutes;
}

function timeLabel(totalMinutes: number): string {
  const normalized = totalMinutes % (24 * 60);
  return `${String(Math.floor(normalized / 60)).padStart(2, '0')}:${String(normalized % 60).padStart(2, '0')}`;
}

export function reservationTimeSlots(
  opening: string,
  closing: string,
  selectedDate: string,
  now = new Date(),
): string[] {
  if (!opening || !closing || !isReservationDateAllowed(selectedDate, now)) return [];
  const open = minutesOf(opening);
  let close = minutesOf(closing);
  if (close <= open) close += 24 * 60;
  const nowParts = zonedParts(now);
  const currentMinutes = Number(nowParts['hour']) * 60 + Number(nowParts['minute']);
  const today = localDateInBolivia(now);
  const slots: string[] = [];
  for (
    let start = open;
    start + RESERVATION_SLOT_MINUTES <= close;
    start += RESERVATION_SLOT_MINUTES
  ) {
    const label = timeLabel(start);
    const actualDayOffset = Math.floor(start / (24 * 60));
    if (
      selectedDate === today &&
      actualDayOffset === 0 &&
      start <= currentMinutes
    ) {
      continue;
    }
    slots.push(label);
  }
  return slots;
}

export function reservationTimestamp(date: string, time: string): string {
  return `${date}T${time}:00${RESERVATION_TIMEZONE_OFFSET}`;
}
