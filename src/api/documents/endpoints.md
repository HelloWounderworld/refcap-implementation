# Endpoints que queremos no app.py (claro, os testes nao estao inclusos, porem, eu vou criar como pre-caucao)

## POST/caption

### Request:

```json
{
    "scene_id": "scene_id",
    "video_id": "video_id",
    "program_id": "nome_do_programa_seriado",
    "scene_video_path": "data/scenes/{video_id}/{scene_id}.mp4"
}
```

### Response:
**Precisa desse job_id??? Nao daria para fixar somente para um unico tipo de video?**
```json
{
  "job_id": "9e8adacb...",
  "state": "concluded",
  "resume": {"total": 3, "ok": 3, "erros": 0},
  "items": [
    {
      "scene_id": "cena_01",
      "scene_caption_en": "a woman preparing food in a kitchen",
      "keywords_en": [
        {"token": "woman",   "weight": 0.6},
        {"token": "kitchen", "weight": 0.6},
        {"token": "food",    "weight": 0.6}
      ],
      "model_name": "refcap",
      "model_version": "v1",
      "status": "success"
    }
  ],
  "segundos": 12.4
}
```

**Nao daria para colocar a possibilidade de o status informar o seguinte, caso de algum erro, como abaixo?**

```json
{
  "job_id": "9e8adacb...",
  "estado": "concluido",
  "resumo": {"total": 3, "ok": 3, "erros": 0},
  "items": [
    {
      "scene_id": "cena_01",
      "scene_caption_en": "a woman preparing food in a kitchen",
      "keywords_en": [
        {"token": "woman",   "weight": 0.6},
        {"token": "kitchen", "weight": 0.6},
        {"token": "food",    "weight": 0.6}
      ],
      "model_name": "refcap",
      "model_version": "v1",
      "status": "error",
      "error_code": "INVALID_REQUEST",
      "message": "Invalid Request (alguma coisa do tipo...)"
    }
  ],
  "segundos": 12.4
}
```

**Sendo os erros de codigos sao como o seguinte**

```markdown
INVALID_REQUEST
CAPTION_FAILED
SCENE_NOT_FOUND
FILE_NOT_FOUND
INTERNAL_ERROR
```

## POST/caption/batch

### Request:

```json
{
    "items": [
        {
            "scene_id": "scene_id",
            "video_id": "video_id",
            "program_id": "nome_do_programa_seriado",
            "scene_video_path": "data/scenes/{video_id}/{scene_id}.mp4"
        }
    ]
}
```

## GET/health

```json
{
    "status": "ok",
    "service": "caption-api"
}
```
