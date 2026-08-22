# НТД — нормативно-техническая документация

Этот каталог содержит только нормативные правила управления корпусом НТД.
Исходные PDF, распознанный corpus и object-storage payload в Git не
публикуются.

НТД является постоянной `platform memory`: каждая официально полученная
редакция получает отдельные `SourceVersion` и `NormativeEdition`, provenance,
effective interval и неизменяемую identity bytes. Новая редакция не
перезаписывает старую и не становится применимой автоматически.

## Что допустимо хранить в репозитории

- архитектурные спецификации и ADR;
- схемы и контракты после прохождения соответствующего gate;
- обезличенные synthetic fixtures/goldens после Promotion Gate;
- manifest без content, secret, locator capability и данных конкретного ОКС.

## Что в Git не хранится

- PDF/DOCX/XLSX/DXF НТД или форм;
- ПД/РД, договоры и регламенты Заказчика;
- документы и результаты конкретного ОКС;
- OCR/VLM raw artifacts, embeddings, indexes или model files;
- credentials, access URLs и object-storage keys.

Platform NTD objects размещаются по действующим
`DEPLOYMENT_AND_POLICY_PROFILES_v0.1.md` и
`LIFECYCLE_AND_RETENTION_SPECIFICATION_v0.1.md`. Регламент Заказчика — всегда
workspace source конкретного ОКС; он не является НТД и не может
перезаписывать нормативную редакцию.

Правила формирования и квалификации корпуса описаны в
`NTD_CORPUS_MANAGEMENT_v0.1.md`. Загрузка НТД, создание object storage и
прикладная ingestion implementation не входят в текущий architecture-only
baseline.
