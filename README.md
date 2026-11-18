# Telemetry Sentinel

Otobüsler ile ana istasyon arasındaki veri akışında oluşan kesintilerin **nereden kaynaklandığını** (sensör, otobüs veya ana istasyon) bulan web uygulaması. Fikir roket ve mekik telemetrisinden esinlenmiştir; senaryo otobüs filosu ve ana istasyon olarak uyarlanmıştır.

İstasyon sorumlusu kesinti kayıtlarını içeren CSV dosyasını yükler, sistem kesinti aralıklarının nerede çakıştığına bakar ve her kesinti parçası için sonucu tek cümleyle yazar:

```
00:00:05–00:00:09 arası sorun B1 otobüsünde.
```

## Hızlı başlangıç

### Docker ile (önerilen)

```bash
docker-compose up --build
```

Ardından tarayıcıda **http://localhost:8000** adresini açın. API belgesi **http://localhost:8000/docs** adresindedir.

### Docker olmadan

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn main:app --reload
```

> `index.html` dosyasını doğrudan çift tıklayarak açmayın; analiz Python sunucusunda yapıldığı için sayfa uygulama üzerinden açılmalıdır.

## CSV formatı

Her satır, bir sensörün verisinin istasyona ulaşmadığı zaman aralığıdır. Başlık satırı zorunludur.

```csv
otobus,sensor,baslangic,bitis
B1,S1,00:00:02,00:00:09
B1,S2,00:00:05,00:00:12
```

- Zaman biçimi `SS:DD:ss` (saat:dakika:saniye), tüm veri aynı gün içinde.
- Bitiş anı aralığa dahil değildir: 00:00:05'te biten ile 00:00:05'te başlayan kesinti çakışmaz.
- Excel'in noktalı virgüllü (`;`) CSV çıktısı ve UTF-8 BOM desteklenir.
- Dosyada tek bir hatalı satır varsa analiz yapılmaz; tüm hatalar satır numaralarıyla gösterilir.
- Örnek dosya: [`ornek.csv`](ornek.csv)

## Filo tanımı

Otobüsler ve her otobüsteki sensörler [`filo.json`](filo.json) dosyasında tanımlıdır. Filo değişince kodu değiştirmeye gerek yoktur; Docker ile çalışırken dosyayı düzenleyip sayfayı yenilemek yeterlidir.

```json
{
  "otobusler": ["B1", "B2", "B3"],
  "sensorler": ["S1", "S2", "S3"]
}
```

## Karar kuralları

Kesintiler zaman çizgisinde birbirlerini kestikleri noktalardan parçalara bölünür. Her parça için kurallar şu sırayla denenir:

| Sıra | Durum | Sonuç |
| --- | --- | --- |
| 1 | Filodaki tüm otobüslerin tüm sensörleri aynı anda kesik | Ana istasyon arızası |
| 2 | Bir otobüsün tüm sensörleri aynı anda kesik | Otobüs arızası |
| 3 | Bir otobüste tek veya birkaç sensör kesik | Sensör arızası |

## Proje yapısı

```
├── main.py                  FastAPI sunucusu
├── index.html               Arayüz (sonucu sunucudan alıp gösterir)
├── filo.json                Otobüs ve sensör listesi
├── ornek.csv                Örnek kesinti dosyası
├── src/
│   ├── parser.py            CSV okuma ve girdi doğrulama
│   └── decision_engine.py   Üç aşamalı karar motoru
├── tests/
│   ├── test_engine.py       Doğruluk (D1–D9), esneklik, performans
│   ├── test_parser.py       Hatalı veri, güvenlik, Excel uyumluluğu
│   └── test_api.py          API uçtan uca ve güvenlik testleri (G1–G6)
├── Dockerfile
└── docker-compose.yml
```

## Test ve kalite kontrolleri

```bash
pytest --cov=src tests/       # birim + API testleri ve kod kapsama (hedef ≥ %85)
radon cc src/ -a              # döngüsel karmaşıklık (hedef V(G) < 10)
flake8 src/ tests/ main.py    # PEP8 ve McCabe karmaşıklık sınırı
```

Her `git push` sonrasında aynı kontroller GitHub Actions üzerinde otomatik çalışır ([`ci.yml`](.github/workflows/ci.yml)).

## Bilinen sınırlar

- Zamanlar saniye hassasiyetindedir; tolerans yoktur.
- Filonun tamamı kesilmedikçe istasyon arızası kararı verilmez. Filoda tek otobüs varsa istasyon ve otobüs arızası ayırt edilemez, bu durumda otobüs arızası denir.
- Gece yarısını geçen kesintiler desteklenmez.
- Sonuçlar kaydedilmez, yalnızca ekranda gösterilir.
- Kimlik doğrulama yoktur; uygulama istasyonun iç ağında çalışacak şekilde tasarlanmıştır.
