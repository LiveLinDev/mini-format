# 404 real en nginx (soft-404 de mini-format.pmoluna.com)

**Estado:** el sitio publicado responde `200` con la portada a cualquier ruta inexistente
(`/no-existe-xyz/`, `/en/taller/`, `/source/experiments/v8_sima/`...). Eso se llama *soft-404*: los enlaces
rotos parecen vivos, los buscadores indexan páginas que no existen y cualquier comprobación de
`code == 200` da por buena una ruta ausente.

**Causa (reportada en `sitio/desplegar.sh`, no verificable desde el repositorio):** el `server` de nginx
usa `try_files $uri $uri/ /index.html;`. **El `nginx.conf` del servidor no está en este repositorio** y la
llave de despliegue (`restrict,command=`) no puede editarlo, así que **esto solo se arregla en el servidor,
con la llave personal de quien lo administra**. Ni el repositorio ni el workflow lo arreglan: lo único que
hace el repositorio es entregar la página (`sitio/404.html`) y detectar el problema
(`tools/verificar_publicacion.py`).

## Cambio que hay que hacer en el servidor

En el `server { ... }` de `mini-format.pmoluna.com`, sustituir el fallback a `index.html` por un 404 real y
declarar la página de error:

```nginx
try_files $uri $uri/ =404;
error_page 404 /404.html;
```

Dentro del bloque `location /` (o del `server` si no hay `location`), es decir:

```nginx
server {
    root /var/www/mini-format;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }
    error_page 404 /404.html;
    location = /404.html {
        # se sirve solo como página de error, y se puede pedir directamente
        # (quita `internal;` si quieres que tools/verificar_publicacion.py vea 200 en /404.html)
        internal;
    }
}
```

`sitio/404.html` ya se publica en la raíz (`/var/www/mini-format/404.html`). Es bilingüe (ES/EN), lleva
`noindex` y usa rutas absolutas (`/base.css`, `/docs.js`...), así que se ve bien sea cual sea la URL que falló.
Nginx **conserva el código 404** al servirla con `error_page`: no hay redirección.

### Pasos

1. Copia de seguridad: `sudo cp /etc/nginx/sites-available/<sitio> /etc/nginx/sites-available/<sitio>.bak`.
2. Edita el `server` como arriba.
3. `sudo nginx -t` (debe decir `syntax is ok` y `test is successful`).
4. `sudo systemctl reload nginx` (recarga sin cortar conexiones).
5. Comprueba desde cualquier máquina:

   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' https://mini-format.pmoluna.com/no-existe-xyz/   # 404
   curl -s -o /dev/null -w '%{http_code}\n' https://mini-format.pmoluna.com/                 # 200
   python tools/verificar_publicacion.py --esperado <sha>
   ```

   Con el arreglo, `verificar_publicacion.py` informa «404 real» y deja de emitir la advertencia de soft-404.
6. Marcha atrás: restaurar el `.bak` y `sudo systemctl reload nginx`.

## Consecuencias que conviene saber

* Las rutas que el sitio **nunca** ha publicado pasan a dar 404. Antes del despliegue de este cambio de
  repositorio eso incluye `/validacion/`, `/economia/` y las copias `/en/taller/`, `/en/sima/`, `/en/ejemplo/`
  (las páginas bilingües en línea no tienen copia `/en/`: ver `sitio/publicar.py`, `RUTAS_EN_LINEA`).
* La regla de nginx «niega rutas con punto» (`.nuevo`, `.anterior` del receptor de despliegue) debe seguir
  activa; `try_files ... =404` no la sustituye.
* Antes de recargar nginx, publica primero el sitio nuevo (con `404.html`): si no, `error_page` apuntaría a un
  archivo que no existe y nginx respondería su 404 por omisión (sin marca del sitio, pero con el código correcto).

## Qué sigue dependiendo del servidor

| Comportamiento | Dónde se arregla | Quién |
|---|---|---|
| 404 real en lugar de soft-404 | `nginx.conf` del servidor (este documento) | administrador del servidor |
| Cabeceras `Cache-Control` / CSP | `nginx.conf` | administrador del servidor |
| Que el despliegue llegue (Actions, secretos, entorno `produccion`) | GitHub Actions y el servidor | quien tiene acceso |
