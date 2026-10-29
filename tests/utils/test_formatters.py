from app.utils.formatters import format_name, format_short_name, mask_cnpj, mask_cpf


def test_format_short_name_no_preposition():
    assert format_short_name("Lume Nilo") == "Lume Nilo"


def test_format_short_name_with_preposition_de():
    assert format_short_name("Clara de Lira") == "Clara Lira"


def test_format_short_name_with_preposition_da():
    assert format_short_name("Jardim Sol da Agostinho") == "Jardim Sol"


def test_format_short_name_with_preposition_do():
    assert format_short_name("Joao do Pulo") == "Joao Pulo"


def test_format_short_name_with_preposition_dos():
    assert format_short_name("Carlos dos Flora Nevoa") == "Carlos Flora"


def test_format_short_name_with_preposition_das():
    assert format_short_name("Ana das Neves") == "Ana Neves"


def test_format_short_name_single_name():
    assert format_short_name("Lume") == "Lume"


def test_format_short_name_empty():
    assert format_short_name("") == ""
    assert format_short_name(None) == ""


def test_mask_cnpj():
    assert mask_cnpj("12345678000195") == "12.345.678/0001-95"
    assert mask_cnpj("") == ""
    assert mask_cnpj(None) is None
    assert mask_cnpj("123") == "123"


def test_mask_cpf():
    assert mask_cpf("12345678901") == "123.456.789-01"
    assert mask_cpf("") == ""
    assert mask_cpf(None) is None
    assert mask_cpf("123") == "123"


def test_format_name():
    assert format_name("lume da nilo") == "Lume da Nilo"
    assert format_name("ze do carmo") == "Ze do Carmo"
    assert format_name("JARDIM DAS GRACAS") == "Jardim das Gracas"
    assert format_name("ana de almeida") == "Ana de Almeida"
    assert format_name("") == ""
    assert format_name("   ") == "   "
    assert format_name(None) is None
