# WMS Frontend

Ito ang active Vue 3 + Vite frontend ng WMS application. Ang Django REST API ay
nasa katabing `../backend/` folder.

## Local development

```powershell
Set-Location C:\proj\wms-web-ui\frontend
npm install
npm run dev
```

Buksan ang `http://localhost:5173`. Sa development, ipinapasa ng Vite ang
requests na `/api/...` sa `http://127.0.0.1:8000`.

## Checks

```powershell
npm test
npm run build
```

Para sa hiwalay o deployed na API host, gumawa ng `.env.production` o ang
naaangkop na Vite environment file:

```dotenv
VITE_API_BASE_URL=/api
```

Huwag ilagay rito ang database credentials o Django secret key. Ang mga iyon ay
backend secrets at dapat manatili sa `../backend/.env` o sa approved secret store.
