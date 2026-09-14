const reservationWindowDays = 7;
const reservationSlotMinutes = 30;

class ReservationDay {
  const ReservationDay({required this.value, required this.date});
  final String value;
  final DateTime date;
}

DateTime boliviaNow([DateTime? now]) =>
    (now ?? DateTime.now()).toUtc().subtract(const Duration(hours: 4));

List<ReservationDay> upcomingReservationDays([DateTime? now]) {
  final local = boliviaNow(now);
  final start = DateTime.utc(local.year, local.month, local.day);
  return List.generate(reservationWindowDays, (index) {
    final date = start.add(Duration(days: index));
    return ReservationDay(value: _dateValue(date), date: date);
  }, growable: false);
}

List<String> reservationTimeSlots({
  required String opening,
  required String closing,
  required String selectedDate,
  DateTime? now,
}) {
  final days = upcomingReservationDays(now);
  if (!days.any((day) => day.value == selectedDate)) return const [];
  final open = _minutes(opening);
  var close = _minutes(closing);
  if (open == null || close == null || close == open) return const [];
  if (close < open) close += 24 * 60;
  final localNow = boliviaNow(now);
  final currentMinutes = localNow.hour * 60 + localNow.minute;
  final today = _dateValue(
    DateTime.utc(localNow.year, localNow.month, localNow.day),
  );
  final slots = <String>[];
  for (
    var start = open;
    start + reservationSlotMinutes <= close;
    start += reservationSlotMinutes
  ) {
    final dayOffset = start ~/ (24 * 60);
    if (selectedDate == today && dayOffset == 0 && start <= currentMinutes) {
      continue;
    }
    slots.add(_timeValue(start));
  }
  return slots;
}

int? _minutes(String value) {
  final match = RegExp(r'^(\d{2}):(\d{2})').firstMatch(value);
  if (match == null) return null;
  final hours = int.tryParse(match.group(1)!);
  final minutes = int.tryParse(match.group(2)!);
  if (hours == null || minutes == null || hours > 23 || minutes > 59) {
    return null;
  }
  return hours * 60 + minutes;
}

String _dateValue(DateTime value) =>
    '${value.year.toString().padLeft(4, '0')}-'
    '${value.month.toString().padLeft(2, '0')}-'
    '${value.day.toString().padLeft(2, '0')}';

String _timeValue(int minutes) {
  final normalized = minutes % (24 * 60);
  return '${(normalized ~/ 60).toString().padLeft(2, '0')}:'
      '${(normalized % 60).toString().padLeft(2, '0')}';
}
