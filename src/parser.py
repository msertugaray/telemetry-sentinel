"""CSV okuma, filo tanımı ve girdi doğrulama.

Beklenen CSV formatı (başlık satırı zorunlu):

    otobus,sensor,baslangic,bitis
    B1,S1,00:00:02,00:00:09

Her satır, bir sensörün verisinin istasyona ulaşmadığı zaman aralığını
gösterir. Zamanlar saat:dakika:saniye biçimindedir ve tüm veri aynı gün
içindedir. Bitiş anı aralığa dahil değildir: 00:00:05'te biten bir kesinti
ile 00:00:05'te başlayan bir kesinti çakışmaz.
"""

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

HEADER = ("otobus", "sensor", "baslangic", "bitis")
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d):([0-5]\d)$")
MAX_ROWS = 100_000
MAX_REPORTED_ERRORS = 20


@dataclass(frozen=True)
class Fleet:
    """Filodaki otobüsler ve her otobüste bulunan sensörler (otobüsler özdeş)."""

    buses: tuple
    sensors: tuple


@dataclass(frozen=True)
class Outage:
    """Bir sensörde [start, end) aralığında yaşanan veri kesintisi (saniye)."""

    bus: str
    sensor: str
    start: int
    end: int
    line: int = field(default=0, compare=False)


@dataclass(frozen=True)
class RowError:
    """Kullanıcıya gösterilecek, satır numaralı hata."""

    line: int
    message: str

    def __str__(self):
        if self.line == 0:
            return self.message
        return f"{self.line}. satır: {self.message}"


class FleetError(ValueError):
    """filo.json okunamadığında veya geçersiz olduğunda fırlatılır."""


class CsvFormatError(ValueError):
    """CSV dosyasında bir veya daha fazla hata bulunduğunda fırlatılır."""

    def __init__(self, errors):
        self.errors = errors[:MAX_REPORTED_ERRORS]
        self.total = len(errors)
        super().__init__("; ".join(str(e) for e in self.errors))


# --------------------------------------------------------------------------
# Filo tanımı
# --------------------------------------------------------------------------

def _clean_name_list(value, key):
    if not isinstance(value, list) or not value:
        raise FleetError(f"filo.json: '{key}' boş olmayan bir liste olmalı")
    names = [str(item).strip() for item in value]
    if any(not name for name in names):
        raise FleetError(f"filo.json: '{key}' içinde boş isim var")
    if len(set(names)) != len(names):
        raise FleetError(f"filo.json: '{key}' içinde tekrar eden isim var")
    return tuple(names)


def fleet_from_dict(data):
    """Sözlükten Fleet nesnesi üretir ve doğrular."""
    if not isinstance(data, dict):
        raise FleetError("filo.json bir JSON nesnesi olmalı")
    buses = _clean_name_list(data.get("otobusler"), "otobusler")
    sensors = _clean_name_list(data.get("sensorler"), "sensorler")
    return Fleet(buses=buses, sensors=sensors)


def load_fleet(path):
    """filo.json dosyasını okuyup Fleet nesnesine çevirir."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FleetError(f"filo.json okunamadı: {exc}") from exc
    return fleet_from_dict(data)


# --------------------------------------------------------------------------
# Zaman dönüşümleri
# --------------------------------------------------------------------------

def parse_time(text):
    """'SS:DD:ss' biçimindeki zamanı gün başından itibaren saniyeye çevirir."""
    match = TIME_PATTERN.match(text.strip())
    if not match:
        raise ValueError(f"geçersiz zaman '{text}' (beklenen biçim SS:DD:ss)")
    hours, minutes, seconds = (int(part) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def format_time(total_seconds):
    """Saniyeyi 'SS:DD:ss' biçimine çevirir."""
    hours, rest = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


# --------------------------------------------------------------------------
# CSV okuma
# --------------------------------------------------------------------------

def _detect_delimiter(text):
    """Türkçe Excel noktalı virgül kullandığı için ayracı ilk satırdan seçer."""
    first_line = text.split("\n", 1)[0]
    if ";" in first_line and "," not in first_line:
        return ";"
    return ","


def _read_rows(text):
    """Boş olmayan satırları (satır numarası, hücreler) olarak döndürür."""
    reader = csv.reader(io.StringIO(text), delimiter=_detect_delimiter(text))
    rows = []
    for cells in reader:
        if any(cell.strip() for cell in cells):
            rows.append((reader.line_num, [cell.strip() for cell in cells]))
    return rows


def _check_header(rows):
    if not rows:
        raise CsvFormatError([RowError(0, "Dosya boş.")])
    line, cells = rows[0]
    if tuple(cell.lower() for cell in cells) != HEADER:
        expected = ",".join(HEADER)
        raise CsvFormatError([RowError(line, f"başlık satırı '{expected}' olmalı")])
    if len(rows) - 1 > MAX_ROWS:
        raise CsvFormatError([RowError(0, f"En fazla {MAX_ROWS} kayıt yüklenebilir.")])


def _parse_row(line, cells, fleet):
    """Tek bir veri satırını Outage nesnesine çevirir; hata varsa ValueError."""
    if len(cells) != len(HEADER):
        raise ValueError(f"{len(HEADER)} sütun bekleniyor, {len(cells)} bulundu")
    bus, sensor, start_text, end_text = cells
    if bus not in fleet.buses:
        raise ValueError(f"tanımsız otobüs '{bus}'")
    if sensor not in fleet.sensors:
        raise ValueError(f"tanımsız sensör '{sensor}'")
    start = parse_time(start_text)
    end = parse_time(end_text)
    if start >= end:
        raise ValueError("başlangıç zamanı bitişten küçük olmalı")
    return Outage(bus, sensor, start, end, line)


def _find_duplicates(outages):
    """Aynı sensör için birbiriyle çakışan kayıtları bulur."""
    errors = []
    by_sensor = {}
    for outage in outages:
        by_sensor.setdefault((outage.bus, outage.sensor), []).append(outage)
    for (bus, sensor), items in by_sensor.items():
        items.sort(key=lambda o: o.start)
        for previous, current in zip(items, items[1:]):
            if current.start < previous.end:
                message = (f"{bus}-{sensor} kaydı {previous.line}. satırdaki "
                           "kayıtla çakışıyor")
                errors.append(RowError(current.line, message))
    return errors


def parse_csv(text, fleet):
    """CSV metnini doğrular ve kesinti listesine çevirir.

    Dosyada tek bir hatalı satır bile varsa analiz yapılmaz; tüm hatalar
    satır numaralarıyla birlikte CsvFormatError içinde döndürülür.
    """
    rows = _read_rows(text.lstrip("﻿"))
    _check_header(rows)
    outages, errors = [], []
    for line, cells in rows[1:]:
        try:
            outages.append(_parse_row(line, cells, fleet))
        except ValueError as exc:
            errors.append(RowError(line, str(exc)))
    errors.extend(_find_duplicates(outages))
    if errors:
        errors.sort(key=lambda e: e.line)
        raise CsvFormatError(errors)
    return outages
