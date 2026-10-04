"""What the API takes and answers with. A route returns the forge's own record
and names the model it answers with as its `response_model`, so FastAPI
reads each field off the record by name and sends nothing the model does not
list. A forge type is the model itself where everything it holds may go to
the browser; a model here lists the fields that go out where it holds more,
such as the keys its ids are built from or someone's email.
"""
