# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **2026-01-26**: Corregido error `InvalidArgumentType` en `set-TT.py` al crear tasks. El parámetro `hosts_ordering` ahora usa el enum `HostsOrdering` en lugar de un string. Se agregó manejo de errores mejorado y validación del CSV con filtrado de filas vacías.
- **2026-01-26**: Corregido `export-target.py` para exportar un rango IP por fila en lugar de combinar todos los rangos en una sola fila. Ahora divide los rangos IP por comas y crea una fila CSV por cada rango individual, manteniendo el mismo título y descripción.
