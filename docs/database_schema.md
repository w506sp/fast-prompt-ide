# Veritabanı Şeması ve Veri Modeli

Bu belge, **fast-prompt-ide** projesinin veri mimarisini, varlık (entity) özelliklerini ve ilişkilerini tanımlar.

## Şema (Nomnoml)

```text
[User|
+id: int
+username: string
+email: string
+password: hash
+created_at: datetime
]

[Workspace|
+id: int
+owner_id: int
+name: string
+description: text
+created_at: datetime
]

[Membership|
+id: int
+user_id: int
+workspace_id: int
+role: enum (admin, member, viewer)
+joined_at: datetime
]

[Project|
+id: int
+workspace_id: int
+name: string
+description: text
+created_at: datetime
]

[PromptTemplate|
+id: int
+project_id: int
+name: string
+description: text
+created_at: datetime
+updated_at: datetime
]

[PromptVersion|
+id: int
+template_id: int
+version_number: int
+content: text
+model_name: string
+model_config: jsonb (temp, top_p, etc.)
+commit_message: string
+is_active: boolean
+created_at: datetime
]

[Variable|
+id: int
+version_id: int
+name: string
+description: string
+default_value: text
]

[Execution|
+id: int
+version_id: int
+user_id: int
+input_data: jsonb
+output_text: text
+latency_ms: int
+token_usage: jsonb (prompt, completion)
+status: enum (pending, streaming, success, error, timeout)
+error_message: text
+created_at: datetime
]

[User] -> [Workspace]
[User] -> [Membership]
[Workspace] -> [Membership]
[Workspace] -> [Project]
[Project] -> [PromptTemplate]
[PromptTemplate] -> [PromptVersion]
[PromptVersion] -> [Variable]
[PromptVersion] -> [Execution]
[User] -> [Execution]
```

## Varlık Tanımları ve Rolleri

### 1. Organizasyon Yapısı
*   **User:** Sisteme giriş yapan ve işlemleri gerçekleştiren kullanıcılar.
*   **Workspace:** Kullanıcıların projelerini organize ettiği, ekip çalışmasına temel oluşturabilecek üst seviye alan. Her workspace'in bir `owner`'ı vardır; sahip, üye ekleme/çıkarma ve workspace silme gibi en yüksek yetkilere sahiptir.
*   **Membership:** Kullanıcı–workspace ilişkisini ve kullanıcının workspace içindeki rolünü (`admin`, `member`, `viewer`) tutan ara tablo. `viewer` salt okunur; `member` ve `admin` proje/prompt/version oluşturabilir; üye ekleme/çıkarma ve rol değişikliği yalnızca workspace sahibine açıktır.
*   **Project:** Belirli bir amaç (örn: "Müşteri Destek Botu") için oluşturulan prompt koleksiyonu.

### 2. Prompt ve Versiyonlama
*   **PromptTemplate:** Bir promptun ana iskeleti ve kimliğidir.
*   **PromptVersion:** Bir şablonun zaman içindeki değişimlerini tutar. `commit_message` ile yapılan değişikliklerin nedeni, `model_config` ile de model parametreleri (temperature vb.) saklanır.
*   **Variable:** Prompt içindeki `{{değişken}}` alanlarının tanımı ve varsayılan değerleridir.

### 3. Kayıt ve Metrikler
*   **Execution:** Modelin her çalıştırılmasında oluşan kayıt. Girdiler, çıktılar, `latency_ms` (milisaniye cinsinden gecikme) ve `token_usage` (input/output token sayıları) bu tabloda tutularak performans analizi yapılmasına olanak tanır. `status` alanı akış sürecini de yansıtır: `pending` (yeni oluşturuldu), `streaming` (Ollama'dan token'lar geliyor), `success` / `error` / `timeout` (tamamlandı).
