# Odoo Baseline Registry

> Registro formal del runtime y source baseline del proyecto. Cada actualización de Odoo upstream requiere re-verificación de la Capability Matrix y regression testing (ADR-027).

---

## Odoo Source Baseline

| Propiedad | Valor |
|---|---|
| Repository | `odoo/odoo` |
| Branch | `19.0` |
| Verified Commit | `95f76213d3f732f1d198c740a908e8037c376114` |
| Capability Matrix | [00-odoo19-capability-matrix.md](../01-dominios/00-odoo19-capability-matrix.md) |
| Verification Date | 2026-08-18 |

> **Nota**: Este commit fue verificado manualmente contra la Capability Matrix para confirmar la existencia de campos y métodos documentados en `stock.quant`, `stock.package`, `stock.location`, etc.

---

## Odoo Runtime Baseline

| Propiedad | Valor |
|---|---|
| Image Tag | `odoo:19.0` |
| Index Digest | `sha256:4a96c54e7ccddc83ab3baba00be8f7cac418cbd5bd0291247ed1bba8bbd5d5e7` |
| linux/amd64 Digest | `sha256:58ddf2d09623931292435f00d6cc0d9c25b0382636c3ff6037e43abfb698fa29` |
| Odoo Version | `19.0-20260817` |
| Base Image | `ubuntu:noble` |
| Docker Source Revision | `5930f757f9a968416ed835e59539197ada442956` |
| Pinned Date | 2026-08-18 |
| Pinned In | `docker/odoo/Dockerfile` (`FROM odoo:19.0@sha256:...`) |

> **Decisión**: El `FROM` en el Dockerfile usa el **index digest** (no el manifest específico de plataforma). Docker resuelve automáticamente al manifest correcto para la plataforma local. El `linux/amd64 digest` se registra aquí para verificación en Kubernetes producción.

---

## WMS Project Baseline

| Propiedad | Valor |
|---|---|
| Architecture Baseline Tag | `v0.0.0-baseline` (commit `44dfb55`) |
| Branch | `develop` |
| Status | BOOT EPIC en progreso |

---

## Protocolo de Actualización

Cuando se necesite actualizar Odoo upstream:

1. **Obtener nuevo digest**: `docker buildx imagetools inspect odoo:19.0`
2. **Verificar Capability Matrix**: Comparar campos/métodos contra `docs/01-dominios/00-odoo19-capability-matrix.md`
3. **Actualizar Dockerfile**: Nuevo `@sha256:...`
4. **Actualizar este registro**: Nuevos digests y fecha
5. **Ejecutar regression tests**: Todos los módulos WMS instalados
6. **Commit**: Con referencia a ADR-027

> [!WARNING]
> No actualizar el digest sin re-verificar la Capability Matrix. Un cambio upstream puede romper campos o métodos que los módulos WMS esperan.

---

*Documento creado para BOOT-003 (ADR-027). Referencia: [ADR-027](../05-decisiones/01-adr.md#adr-027).*
