"""The Unicon backend: the HTTP shell over the `forge` package. Routes,
cookies, the Origin check and the OpenAPI document, started by `unicon api`.
It calls the package's services and never touches a table or a forge
implementation.
"""
