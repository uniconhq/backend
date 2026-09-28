"""The Unicon backend: the HTTP shell over the `forge` package. Routes,
cookies, the Origin check and the OpenAPI document, started by `unicon api`.
It reaches forge through `forge.api` and nothing else of the package: no
table, no transaction, no setting and no forge implementation.
"""
