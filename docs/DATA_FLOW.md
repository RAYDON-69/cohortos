# Data-flow diagram (text)

```
[Staff phone] --OTP--> [Auth DB] --JWT--> [Electron / Browser]
                                              |
                                              v
                                    [FastAPI localhost]
                                       /    |    \
                                      v     v     v
                              [Tenant SQLite] [Chroma RAG] [Local GGUF optional]
                                      |
                                      v
                              [SMS / bKash later]

Cloud LLM (optional, default OFF):
  [Redacted prompt] --> [Groq/NIM/OpenAI/...] --> [Answer]
```

Student CSV import: File → preview (client/server) → admit_student → Tenant SQLite.
