"""Karar motoru testleri (Correctness, Flexibility, Efficiency, Reusability).

Senaryo numaraları proje dokümanındaki doğruluk tablosuyla (D1–D9) aynıdır.
Zamanlar saniye cinsindendir: 2 = 00:00:02.
"""

import random
import time

import pytest
from conftest import make_csv

from src.decision_engine import BUS, SENSOR, STATION, Finding, analyze, summarize
from src.parser import Fleet, Outage, parse_csv

ALL = ("S1", "S2", "S3")


def outages_for(bus, sensors, start, end):
    return [Outage(bus, s, start, end) for s in sensors]


def result(outages, fleet):
    """Kararları (başlangıç, bitiş, kaynak, otobüs, sensörler) demetlerine çevirir."""
    return [(f.start, f.end, f.source, f.bus, f.sensors) for f in analyze(outages, fleet)]


# --------------------------------------------------------------------------
# Doğruluk senaryoları (D1–D9)
# --------------------------------------------------------------------------

def test_d1_tek_sensor(fleet):
    outages = [Outage("B1", "S1", 2, 9)]
    assert result(outages, fleet) == [(2, 9, SENSOR, "B1", ("S1",))]


def test_d2_bir_otobusun_tumu(fleet):
    outages = outages_for("B1", ALL, 2, 9)
    assert result(outages, fleet) == [(2, 9, BUS, "B1", ())]


def test_d3_tum_filo_istasyon(fleet):
    outages = [o for bus in fleet.buses for o in outages_for(bus, ALL, 2, 9)]
    assert result(outages, fleet) == [(2, 9, STATION, None, ())]


def test_d4_kismi_cakisma(fleet):
    outages = [
        Outage("B1", "S1", 2, 9),
        Outage("B1", "S2", 5, 12),
        Outage("B1", "S3", 5, 10),
    ]
    assert result(outages, fleet) == [
        (2, 5, SENSOR, "B1", ("S1",)),
        (5, 9, BUS, "B1", ()),
        (9, 10, SENSOR, "B1", ("S2", "S3")),
        (10, 12, SENSOR, "B1", ("S2",)),
    ]


def test_d5_oncelik_istasyon_otobusten_once(fleet):
    outages = [o for bus in fleet.buses for o in outages_for(bus, ALL, 5, 9)]
    outages += outages_for("B1", ALL, 2, 5)
    assert result(outages, fleet) == [
        (2, 5, BUS, "B1", ()),
        (5, 9, STATION, None, ()),
    ]


def test_d6_filonun_bir_kismi_istasyon_degil(fleet):
    outages = outages_for("B1", ALL, 2, 9) + outages_for("B2", ALL, 2, 9)
    assert result(outages, fleet) == [
        (2, 9, BUS, "B1", ()),
        (2, 9, BUS, "B2", ()),
    ]


def test_d7_uc_uca_degen_araliklar_cakismaz(fleet):
    outages = [Outage("B1", "S1", 2, 5), Outage("B1", "S2", 5, 9)]
    assert result(outages, fleet) == [
        (2, 5, SENSOR, "B1", ("S1",)),
        (5, 9, SENSOR, "B1", ("S2",)),
    ]


def test_d8_saniye_hassasiyeti(fleet):
    outages = [
        Outage("B1", "S1", 2, 9),
        Outage("B1", "S2", 3, 9),
        Outage("B1", "S3", 3, 9),
    ]
    assert result(outages, fleet) == [
        (2, 3, SENSOR, "B1", ("S1",)),
        (3, 9, BUS, "B1", ()),
    ]


def test_d9_kesinti_yok(fleet):
    outages = parse_csv(make_csv(), fleet)
    assert analyze(outages, fleet) == []


# --------------------------------------------------------------------------
# Ek doğruluk durumları
# --------------------------------------------------------------------------

def test_ayni_karar_uc_uca_gelince_birlesir(fleet):
    outages = [Outage("B2", "S1", 2, 5), Outage("B2", "S1", 5, 8)]
    assert result(outages, fleet) == [(2, 8, SENSOR, "B2", ("S1",))]


def test_bosluklu_kesintiler_ayri_kalir(fleet):
    outages = [Outage("B2", "S1", 2, 5), Outage("B2", "S1", 7, 8)]
    assert result(outages, fleet) == [
        (2, 5, SENSOR, "B2", ("S1",)),
        (7, 8, SENSOR, "B2", ("S1",)),
    ]


def test_istasyondan_sonra_bir_otobus_devam_ediyor(fleet):
    outages = [o for bus in fleet.buses for o in outages_for(bus, ALL, 2, 5)]
    outages += outages_for("B3", ALL, 5, 7)
    assert result(outages, fleet) == [
        (2, 5, STATION, None, ()),
        (5, 7, BUS, "B3", ()),
    ]


def test_tek_otobuslu_filoda_istasyon_karari_verilmez():
    single = Fleet(buses=("B1",), sensors=("S1", "S2"))
    outages = outages_for("B1", ("S1", "S2"), 0, 4)
    assert result(outages, single) == [(0, 4, BUS, "B1", ())]


# --------------------------------------------------------------------------
# Çıktı cümleleri
# --------------------------------------------------------------------------

@pytest.mark.parametrize("finding, expected", [
    (Finding(5, 9, STATION), "00:00:05–00:00:09 arası sorun ana istasyonda."),
    (Finding(5, 9, BUS, "B1"), "00:00:05–00:00:09 arası sorun B1 otobüsünde."),
    (Finding(5, 9, SENSOR, "B1", ("S1",)),
     "00:00:05–00:00:09 arası sorun B1 otobüsünün S1 sensöründe."),
    (Finding(5, 9, SENSOR, "B2", ("S2", "S3")),
     "00:00:05–00:00:09 arası sorun B2 otobüsünün S2, S3 sensörlerinde."),
])
def test_mesajlar(finding, expected):
    assert finding.message == expected


def test_to_dict_api_alanlari():
    data = Finding(5, 9, SENSOR, "B1", ("S1",)).to_dict()
    assert data["start_text"] == "00:00:05"
    assert data["end_text"] == "00:00:09"
    assert data["rule"] == 3
    assert data["sensors"] == ["S1"]
    assert data["message"].endswith("S1 sensöründe.")


def test_ozet_sayimlari(fleet):
    outages = [Outage("B1", "S1", 2, 4)] + outages_for("B2", ALL, 6, 8)
    assert summarize(analyze(outages, fleet)) == {STATION: 0, BUS: 1, SENSOR: 1}


# --------------------------------------------------------------------------
# Flexibility: filo değişince kod değişmeden çalışmalı
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bus_count, sensor_count", [(2, 3), (5, 3), (3, 6), (5, 6)])
def test_farkli_filo_boyutlari(bus_count, sensor_count):
    buses = tuple(f"B{i}" for i in range(1, bus_count + 1))
    sensors = tuple(f"S{i}" for i in range(1, sensor_count + 1))
    custom = Fleet(buses, sensors)

    station = [o for bus in buses for o in outages_for(bus, sensors, 0, 5)]
    assert result(station, custom) == [(0, 5, STATION, None, ())]

    one_bus = outages_for(buses[-1], sensors, 0, 5)
    assert result(one_bus, custom) == [(0, 5, BUS, buses[-1], ())]

    partial = outages_for(buses[0], sensors[:-1], 0, 5)
    assert result(partial, custom) == [(0, 5, SENSOR, buses[0], sensors[:-1])]


# --------------------------------------------------------------------------
# Efficiency: NF1 hedefi 1.000 satır için 2 saniyenin altı
# --------------------------------------------------------------------------

def _random_csv(row_count, fleet, seed=42):
    rng = random.Random(seed)
    rows, cursor = [], {}
    for _ in range(row_count):
        bus = rng.choice(fleet.buses)
        sensor = rng.choice(fleet.sensors)
        start = cursor.get((bus, sensor), 0) + rng.randint(0, 5)
        end = start + rng.randint(1, 10)
        cursor[(bus, sensor)] = end
        rows.append((bus, sensor, _fmt(start), _fmt(end)))
    return make_csv(*rows)


def _fmt(seconds):
    hours, rest = divmod(seconds, 3600)
    return f"{hours:02d}:{rest // 60:02d}:{rest % 60:02d}"


@pytest.mark.parametrize("row_count, limit", [(1_000, 2.0), (10_000, 10.0)])
def test_performans(fleet, row_count, limit):
    text = _random_csv(row_count, fleet)
    started = time.perf_counter()
    analyze(parse_csv(text, fleet), fleet)
    assert time.perf_counter() - started < limit
