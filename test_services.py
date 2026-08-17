from app.services import clean_text, render_template, content_hash

def test_clean():
    assert clean_text(" a   b \n\n\n c ") == "a b\n\nc"

def test_template():
    assert render_template("X\n{POST_TEXT}", "hello") == "X\nhello"

def test_hash():
    assert content_hash("x") == content_hash("x")
