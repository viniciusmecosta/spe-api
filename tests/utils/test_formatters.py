from app.utils.formatters import format_short_name

def test_format_short_name_no_preposition():
    assert format_short_name("Vinicius Costa") == "Vinicius Costa"

def test_format_short_name_with_preposition_de():
    assert format_short_name("Andressa de Sousa") == "Andressa Sousa"

def test_format_short_name_with_preposition_da():
    assert format_short_name("Maria Valeria da Agostinho") == "Maria Valeria"

def test_format_short_name_with_preposition_do():
    assert format_short_name("Joao do Pulo") == "Joao Pulo"

def test_format_short_name_with_preposition_dos():
    assert format_short_name("Carlos dos Santos Silva") == "Carlos Santos"

def test_format_short_name_with_preposition_das():
    assert format_short_name("Ana das Neves") == "Ana Neves"

def test_format_short_name_single_name():
    assert format_short_name("Vinicius") == "Vinicius"

def test_format_short_name_empty():
    assert format_short_name("") == ""
    assert format_short_name(None) == ""
