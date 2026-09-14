import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/reservations/reservation_schedule.dart';

void main() {
  test('genera exactamente los próximos siete días en horario Bolivia', () {
    final days = upcomingReservationDays(DateTime.utc(2026, 9, 14, 2));

    expect(days, hasLength(7));
    expect(days.first.value, '2026-09-13');
    expect(days.last.value, '2026-09-19');
  });

  test('genera slots de 30 minutos y descarta horarios pasados de hoy', () {
    final slots = reservationTimeSlots(
      opening: '09:00:00',
      closing: '13:00:00',
      selectedDate: '2026-09-13',
      now: DateTime.utc(2026, 9, 13, 16, 10),
    );

    expect(slots, ['12:30']);
  });

  test('soporta el horario real que cruza medianoche', () {
    final slots = reservationTimeSlots(
      opening: '22:00:00',
      closing: '01:00:00',
      selectedDate: '2026-09-14',
      now: DateTime.utc(2026, 9, 13, 16),
    );

    expect(slots, ['22:00', '22:30', '23:00', '23:30', '00:00', '00:30']);
  });
}
