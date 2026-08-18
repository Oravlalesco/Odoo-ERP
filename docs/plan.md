# ⚠️ SUPERSEDED — Plan Maestro v1.0

> **Este documento es histórico. No debe usarse para implementación.**
>
> La arquitectura actual se encuentra en `docs/README.md` y sus subdirectorios.

## Arquitectura actual

```text
docs/
├── README.md                ← Índice maestro y changelog
├── 00-vision/               ← Visión del producto
├── 01-dominios/             ← Domain architecture (v1.2)
├── 02-operaciones/          ← RF, exceptions, control tower
├── 03-plataforma/           ← Transaction arch, K8s, NFR, DEV/PROD
├── 04-roadmap/              ← Programas A-G (v1.2)
├── 05-decisiones/           ← 27 ADRs + phase template
└── archive/plan-v1.0.md     ← Este documento
```

## Historia

- **v1.0** (original): Documento monolítico de 2,272 líneas. Sirvió como base para la descomposición en dominios.
- **v1.1**: Correcciones arquitectónicas contra Odoo 19 (ADR-011 a ADR-024).
- **v1.2**: Correcciones quirúrgicas (ADR-025 a ADR-027). Architecture Baseline Candidate.

---

*El documento original completo se encuentra en [plan-v1.0.md](archive/plan-v1.0.md).*
