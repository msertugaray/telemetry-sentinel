"""Üç aşamalı arıza karar motoru.

Kesinti aralıkları zaman çizgisinde birbirlerini kestikleri noktalardan
parçalara bölünür ve her parça için kurallar öncelik sırasıyla uygulanır:

1. Filodaki tüm otobüslerin tüm sensörleri kesik  -> ana istasyon arızası
2. Bir otobüsün tüm sensörleri kesik              -> otobüs arızası
3. Bir otobüste tek veya birkaç sensör kesik       -> sensör arızası

Filoda tek otobüs varsa istasyon ile otobüs arızası birbirinden ayırt
edilemez; bu durumda istasyon kuralı uygulanmaz.
"""

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace

from src.parser import format_time

STATION = "istasyon"
BUS = "otobus"
SENSOR = "sensor"

RULE_NUMBERS = {STATION: 1, BUS: 2, SENSOR: 3}


@dataclass(frozen=True)
class Finding:
    """Bir zaman aralığı için verilen arıza kararı."""

    start: int
    end: int
    source: str
    bus: str = None
    sensors: tuple = ()

    @property
    def window(self):
        return f"{format_time(self.start)}–{format_time(self.end)}"

    @property
    def message(self):
        """İstasyon sorumlusuna gösterilecek tek cümlelik sonuç."""
        prefix = f"{self.window} arası sorun"
        if self.source == STATION:
            return f"{prefix} ana istasyonda."
        if self.source == BUS:
            return f"{prefix} {self.bus} otobüsünde."
        names = ", ".join(self.sensors)
        noun = "sensöründe" if len(self.sensors) == 1 else "sensörlerinde"
        return f"{prefix} {self.bus} otobüsünün {names} {noun}."

    def to_dict(self):
        data = asdict(self)
        data.update(
            sensors=list(self.sensors),
            start_text=format_time(self.start),
            end_text=format_time(self.end),
            rule=RULE_NUMBERS[self.source],
            message=self.message,
        )
        return data


def _segments(outages):
    """Kesintileri, içinde durumun değişmediği [başlangıç, bitiş) parçalarına böler.

    Her parça için {otobüs: kesik sensörler kümesi} döndürür. Olay tabanlı
    tarama kullanıldığı için büyük dosyalarda da doğrusal-logaritmik çalışır.
    """
    events = defaultdict(list)
    for outage in outages:
        key = (outage.bus, outage.sensor)
        events[outage.start].append((key, 1))
        events[outage.end].append((key, -1))

    active = Counter()
    times = sorted(events)
    for current, following in zip(times, times[1:]):
        for key, delta in events[current]:
            active[key] += delta
            if active[key] == 0:
                del active[key]
        if active:
            down = defaultdict(set)
            for bus, sensor in active:
                down[bus].add(sensor)
            yield current, following, down


def _classify(down, fleet, start, end):
    """Tek bir zaman parçası için kuralları öncelik sırasıyla uygular."""
    all_sensors = set(fleet.sensors)
    fully_down = {bus for bus in fleet.buses if down.get(bus, set()) >= all_sensors}

    if len(fleet.buses) > 1 and len(fully_down) == len(fleet.buses):
        return [Finding(start, end, STATION)]

    findings = []
    for bus in fleet.buses:
        if bus in fully_down:
            findings.append(Finding(start, end, BUS, bus))
        elif down.get(bus):
            sensors = tuple(s for s in fleet.sensors if s in down[bus])
            findings.append(Finding(start, end, SENSOR, bus, sensors))
    return findings


def _merge(findings):
    """Aynı kararı veren ve uç uca gelen parçaları birleştirir."""
    merged = []
    last_index = {}
    for finding in findings:
        key = (finding.source, finding.bus, finding.sensors)
        index = last_index.get(key)
        if index is not None and merged[index].end == finding.start:
            merged[index] = replace(merged[index], end=finding.end)
        else:
            last_index[key] = len(merged)
            merged.append(finding)
    return merged


def analyze(outages, fleet):
    """Kesinti listesini analiz edip zaman sırasına göre kararları döndürür."""
    raw = []
    for start, end, down in _segments(outages):
        raw.extend(_classify(down, fleet, start, end))
    return _merge(raw)


def summarize(findings):
    """Arayüzdeki özet kutusu için kaynak türüne göre sayım yapar."""
    counts = Counter(f.source for f in findings)
    return {source: counts.get(source, 0) for source in (STATION, BUS, SENSOR)}
