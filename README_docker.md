Prepare a clean Docker build context and build the image

1. Prepare the context (run from project root):

```powershell
python .\scripts\prepare_docker_context.py
```

2. Build from the prepared context:

```powershell
docker build -t baoan123/chatbot-luat:v1 docker-context
```

If BuildKit causes issues, disable it:

```powershell
$env:DOCKER_BUILDKIT=0; docker build -t baoan123/chatbot-luat:v1 docker-context
```
