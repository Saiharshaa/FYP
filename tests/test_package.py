import verifier


def test_package_importable():
    assert verifier.__version__
