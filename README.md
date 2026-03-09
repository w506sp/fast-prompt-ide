# fast-prompt-ide

**fast-prompt-ide**, yerel dil modellerini (LLM) yönetmek, test etmek ve versiyonlamak için geliştirilmiş, Django tabanlı hafif bir entegre geliştirme ortamıdır (IDE).

## 🚀 Özellikler

- **Model Yönetimi:** Ollama üzerinden çalışan yerel modellerin (Llama 3, Mistral vb.) dinamik seçimi ve yönetimi.
- **Gelişmiş Editör:** Prompt şablonları, dinamik değişken desteği (`{{değişken}}`) ve sözdizimi vurgulama.
- **Versiyon Kontrolü:** Her prompt değişikliği için otomatik sürüm geçmişi ve kolay geri dönüş.
- **Gerçek Zamanlı Yanıt:** HTMX entegrasyonu ile model yanıtlarının (streaming) anlık olarak görüntülenmesi.
- **Performans İzleme:** İşlem bazlı gecikme (latency) ve token kullanım analizi.

## 🛠️ Teknoloji Yığını

- **Backend:** Python 3.10+, Django 5.0+
- **Frontend:** Django Templates, HTMX, Vanilla CSS
- **Veritabanı:** PostgreSQL (veya SQLite)
- **Model Sunucusu:** Ollama

## 📂 Dokümantasyon

Proje ile ilgili detaylı teknik ve yönetimsel dokümanlara `docs/` dizininden erişebilirsiniz:

- [Proje Yönetimi ve Mimari](docs/project_plan.md)
- [Veritabanı Şeması](docs/database_schema.md)

## 🚦 Hızlı Başlangıç

### Gereksinimler
- Python 3.10+
- [Ollama](https://ollama.com/) (Yerel modellerin çalışması için)

### Kurulum
1. Depoyu klonlayın.
2. Sanal ortam oluşturun ve bağımlılıkları yükleyin:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows için: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Veritabanını hazırlayın:
   ```bash
   python manage.py migrate
   ```
4. Uygulamayı başlatın:
   ```bash
   python manage.py runserver
   ```

## 📄 Lisans
Bu proje MIT lisansı ile lisanslanmıştır.
