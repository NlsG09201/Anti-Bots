# Arreglar Twitch `redirect_mismatch`

## Causa real (comprobado en Render)

En tu servicio **Anti-Bots** en Render:

```
TWITCH_CLIENT_ID     = afu46q601sn7xfukiskqrgvz2nkjqw
TWITCH_CLIENT_SECRET = afu46q601sn7xfukiskqrgvz2nkjqw   ← IGUALES (inválido)
```

Son valores de **plantilla**, no una app real de Twitch. Por eso `redirect_mismatch` sigue aunque la URI sea correcta.

## Solución

### 1. Crear app en Twitch

1. [dev.twitch.tv/console/apps](https://dev.twitch.tv/console/apps) → **Register Your Application**
2. **OAuth Redirect URLs** → añade exactamente:

```
https://anti-bots.onrender.com/api/v1/integrations/twitch/callback
```

3. Guarda **Client ID** y **Client Secret** (deben ser **diferentes**).

### 2. Subir a Render

```powershell
cd deploy
.\setup-twitch.ps1
```

Pega Client ID y Secret cuando te lo pida.

### 3. Probar

1. https://anti-bots.vercel.app (no vhbo)
2. Login → Settings → Conectar Twitch

## Verificar

Tras deploy, con sesión iniciada:

```
GET https://anti-bots.onrender.com/api/v1/integrations/twitch/setup
Authorization: Bearer TU_TOKEN
```

Debe devolver `"credentials_ok": true`.
