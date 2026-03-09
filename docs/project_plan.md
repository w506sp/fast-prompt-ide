# Proje Yönetimi ve Mimari Spesifikasyonu

Bu doküman, **fast-prompt-ide** projesinin yönetim süreçlerini, teknik mimarisini ve stratejik planlamasını kapsamaktadır.

## 1. Proje Özeti ve Başlatma Belgesi (Project Charter)
*   **Proje Adı:** fast-prompt-ide
*   **Özet:** fast-prompt-ide, sunucu tarafında barındırılan yerel dil modellerini (LLM) yönetmek, test etmek ve sürümlemek için geliştirilen hızlı ve hafif bir entegre geliştirme ortamıdır. Proje, mimari basitlik ve yüksek performans için saf Django ve Python kütüphaneleri kullanılarak inşa edilmiştir.
*   **Temel Gerekçe:** Kurumsal veri gizliliği ve düşük maliyet için yerel LLM modellerinin verimli yönetimini sağlamak.
*   **Yüksek Seviyeli Hedefler:**
    *   Sunucu tabanlı yerel modellerin sorunsuz entegrasyonu.
    *   Yalın (saf Django) mimari ile ölçeklenebilir altyapı.

## 2. Kapsam Yönetimi ve Temel Fonksiyonlar
*   **Dahil Olanlar:**
    *   **Model Yönetimi:** Sunucudaki Ollama modellerinin (Llama 3, Mistral vb.) dinamik seçimi.
    *   **Gelişmiş Editör:** Prompt şablonları, dinamik değişken desteği (`{{değişken}}`) ve sözdizimi vurgulama.
    *   **Sürüm Kontrolü:** Her prompt değişikliğinin otomatik sürüm geçmişi ve geri dönüş imkanı.
    *   **Gerçek Zamanlı Çıktı:** HTMX ile model yanıtlarının (streaming) anlık olarak arayüzde gösterilmesi.
    *   **Performans İzleme:** İşlem bazlı gecikme (latency) ve sunucu kaynak tüketim analizi.
    *   Django ORM veri yönetimi, Ollama API bağlantısı, Prompt sürümleme sistemi, HTMX reaktif arayüz.
*   **Dahil Olmayanlar:** Harici bulut LLM API'leri, mobil uygulama, paylaşımlı GPU havuzu yönetimi.

## 3. Sistem Mimarisi
*   **Backend:** Django 5.0+ (Asenkron View yapısı).
*   **Veritabanı:** PostgreSQL / SQLite (Prompt ve sürüm verileri için).
*   **Model Sunucusu:** Ollama (Localhost API entegrasyonu).
*   **İletişim Katmanı:** Python `httpx` / `requests` (Ollama REST API ile doğrudan haberleşme).
*   **Frontend:** Django Templates + HTMX (Reaktif kullanıcı deneyimi için).

## 4. Proje Kilometre Taşları (Milestones) ve Yol Haritası
*   **M1 (Hazırlık) - Temel Yapı:** Django proje iskeleti ve Ollama API wrapper katmanının kurulması.
*   **M2 (Veri Katmanı) - Veri Modeli:** Workspace, Project ve Prompt modellerinin (ORM) geliştirilmesi.
*   **M3 (Editör) - Editör ve Sürümleme:** Şablon yönetimi ve sürümleme mantığının kodlanması.
*   **M4 (Reaktivite) - Reaktif Arayüz:** HTMX entegrasyonu ile model yanıtlarının asenkron akışının sağlanması (streaming).
*   **M5 (Final) - İzleme ve Analiz:** Donanım metriklerini raporlayan dashboard'un eklenmesi ve test süreci.

## 5. Risk Kaydı (Risk Register)

| Risk | Etki | Olasılık | Önleme Planı |
| :--- | :--- | :--- | :--- |
| Uzun Yanıt Süreleri | Orta | Yüksek | Django asenkron view ve HTMX streaming kullanımı. |
| Donanım Darboğazı | Yüksek | Orta | Sunucu kaynak izleme ve eşzamanlı istek kısıtlama. |
| İstek Zaman Aşımı | Orta | Orta | HTTP bağlantı zaman aşımlarının optimize edilmesi. |

## 6. Kaynak Planlaması
*   **Teknoloji Yığını:** Python, Django, HTMX, PostgreSQL, Ollama.
*   **Donanım:** Yüksek performanslı merkezi GPU sunucusu.
