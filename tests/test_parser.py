"""CSV okuma ve doğrulama testleri (Reliability, Integrity, Interoperability)."""

import json

import pytest
from conftest import make_csv, t

from src.parser import (
    CsvFormatError,
    FleetError,
    Outage,
    RowError,
    fleet_from_dict,
    format_time,
    load_fleet,
    parse_csv,
    parse_time,
)


def errors_of(text, fleet):
    with pytest.raises(CsvFormatError) as info:
        parse_csv(text, fleet)
    return [str(e) for e in info.value.errors]


# --------------------------------------------------------------------------
# Zaman dönüşümleri
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text, seconds", [
    ("00:00:00", 0),
    ("00:00:09", 9),
    ("01:02:03", 3723),
    ("23:59:59", 86399),
    (" 00:00:05 ", 5),
])
def test_parse_time_gecerli(text, seconds):
    assert parse_time(text) == seconds
    assert format_time(seconds) == text.strip()


@pytest.mark.parametrize("text", [
    "0.00.02", "00:00:02:000", "24:00:00", "00:60:00", "00:00:60", "abc", "",
])
def test_parse_time_gecersiz(text):
    with pytest.raises(ValueError):
        parse_time(text)


# --------------------------------------------------------------------------
# Geçerli dosyalar
# --------------------------------------------------------------------------

def test_gecerli_dosya(fleet):
    text = make_csv(("B1", "S1", t(2), t(9)), ("B2", "S3", t(4), t(6)))
    assert parse_csv(text, fleet) == [
        Outage("B1", "S1", 2, 9),
        Outage("B2", "S3", 4, 6),
    ]


def test_satir_numarasi_saklanir(fleet):
    text = make_csv(("B1", "S1", t(2), t(9)))
    assert parse_csv(text, fleet)[0].line == 2


def test_bos_satirlar_ve_bosluklar_yok_sayilir(fleet):
    text = "otobus,sensor,baslangic,bitis\n\n B1 , S1 , 00:00:02 , 00:00:09 \n\n"
    assert parse_csv(text, fleet) == [Outage("B1", "S1", 2, 9)]


def test_baslik_buyuk_harf_kabul(fleet):
    text = "OTOBUS,Sensor,Baslangic,BITIS\nB1,S1,00:00:02,00:00:09\n"
    assert len(parse_csv(text, fleet)) == 1


def test_uc_uca_kayitlar_ayni_sensorde_gecerli(fleet):
    text = make_csv(("B1", "S1", t(2), t(5)), ("B1", "S1", t(5), t(9)))
    assert len(parse_csv(text, fleet)) == 2


# --------------------------------------------------------------------------
# Interoperability: Excel çıktıları
# --------------------------------------------------------------------------

def test_turkce_excel_noktali_virgul(fleet):
    text = "otobus;sensor;baslangic;bitis\r\nB1;S1;00:00:02;00:00:09\r\n"
    assert parse_csv(text, fleet) == [Outage("B1", "S1", 2, 9)]


def test_utf8_bom(fleet):
    text = "﻿" + make_csv(("B1", "S1", t(2), t(9)))
    assert parse_csv(text, fleet) == [Outage("B1", "S1", 2, 9)]


def test_windows_satir_sonu(fleet):
    text = make_csv(("B1", "S1", t(2), t(9))).replace("\n", "\r\n")
    assert len(parse_csv(text, fleet)) == 1


# --------------------------------------------------------------------------
# Reliability: hatalı veride çökmeden, satır numaralı hata
# --------------------------------------------------------------------------

def test_bos_dosya(fleet):
    assert errors_of("", fleet) == ["Dosya boş."]


def test_eksik_veya_yanlis_baslik(fleet):
    errors = errors_of("B1,S1,00:00:02,00:00:09\n", fleet)
    assert errors[0].startswith("1. satır: başlık satırı")


def test_eksik_sutun(fleet):
    errors = errors_of(make_csv(("B1", "S1", t(2))), fleet)
    assert errors == ["2. satır: 4 sütun bekleniyor, 3 bulundu"]


def test_baslangic_bitisten_buyuk(fleet):
    errors = errors_of(make_csv(("B1", "S1", t(9), t(2))), fleet)
    assert errors == ["2. satır: başlangıç zamanı bitişten küçük olmalı"]


def test_sifir_sureli_kesinti(fleet):
    errors = errors_of(make_csv(("B1", "S1", t(5), t(5))), fleet)
    assert "bitişten küçük" in errors[0]


def test_bozuk_zaman(fleet):
    errors = errors_of(make_csv(("B1", "S1", "99:88:77", t(9))), fleet)
    assert "geçersiz zaman" in errors[0]


def test_tanimsiz_otobus_ve_sensor(fleet):
    text = make_csv(("B9", "S1", t(2), t(9)), ("B1", "S9", t(2), t(9)))
    assert errors_of(text, fleet) == [
        "2. satır: tanımsız otobüs 'B9'",
        "3. satır: tanımsız sensör 'S9'",
    ]


def test_ayni_sensorde_cakisan_kayit(fleet):
    text = make_csv(("B1", "S1", t(2), t(9)), ("B1", "S1", t(5), t(12)))
    assert errors_of(text, fleet) == [
        "3. satır: B1-S1 kaydı 2. satırdaki kayıtla çakışıyor",
    ]


def test_tum_hatalar_birlikte_raporlanir(fleet):
    text = make_csv(
        ("B1", "S1", t(2), t(9)),
        ("B9", "S1", t(2), t(9)),
        ("B1", "S2", "bozuk", t(9)),
    )
    errors = errors_of(text, fleet)
    assert [e.split(".")[0] for e in errors] == ["3", "4"]


def test_hata_listesi_sinirlanir(fleet):
    rows = [("B9", "S1", t(2), t(9))] * 50
    with pytest.raises(CsvFormatError) as info:
        parse_csv(make_csv(*rows), fleet)
    assert info.value.total == 50
    assert len(info.value.errors) == 20


def test_cok_fazla_satir(fleet, monkeypatch):
    monkeypatch.setattr("src.parser.MAX_ROWS", 2)
    rows = [("B1", f"S{i}", t(2), t(9)) for i in (1, 2, 3)]
    assert "En fazla 2 kayıt" in errors_of(make_csv(*rows), fleet)[0]


# --------------------------------------------------------------------------
# Integrity: zararlı içerik
# --------------------------------------------------------------------------

def test_script_iceren_hucre_reddedilir(fleet):
    text = make_csv(("<script>alert(1)</script>", "S1", t(2), t(9)))
    assert "tanımsız otobüs" in errors_of(text, fleet)[0]


def test_csv_olmayan_icerik(fleet):
    assert "başlık satırı" in errors_of("%PDF-1.7\n%âãÏÓ\n", fleet)[0]


def test_row_error_metni():
    assert str(RowError(0, "Dosya boş.")) == "Dosya boş."
    assert str(RowError(4, "hata")) == "4. satır: hata"


# --------------------------------------------------------------------------
# Filo tanımı (filo.json)
# --------------------------------------------------------------------------

def test_load_fleet(tmp_path):
    path = tmp_path / "filo.json"
    path.write_text(json.dumps({"otobusler": ["B1", "B2"], "sensorler": ["S1"]}))
    loaded = load_fleet(path)
    assert loaded.buses == ("B1", "B2")
    assert loaded.sensors == ("S1",)


def test_proje_filo_dosyasi_gecerli():
    from conftest import ROOT
    assert load_fleet(ROOT / "filo.json").buses


@pytest.mark.parametrize("data", [
    [],
    {"otobusler": ["B1"]},
    {"otobusler": [], "sensorler": ["S1"]},
    {"otobusler": ["B1", "B1"], "sensorler": ["S1"]},
    {"otobusler": ["B1", " "], "sensorler": ["S1"]},
])
def test_gecersiz_filo(data):
    with pytest.raises(FleetError):
        fleet_from_dict(data)


def test_okunamayan_filo_dosyasi(tmp_path):
    bad = tmp_path / "filo.json"
    bad.write_text("{bozuk json")
    with pytest.raises(FleetError):
        load_fleet(bad)
    with pytest.raises(FleetError):
        load_fleet(tmp_path / "yok.json")
