def extract_relative_reference(reference: str) -> str:
    """Normalize reference by leaving only relative reference without url prefix and version.

    >>> extract_relative_reference("http://localhost/fhir/Patient/test")
    'Patient/test'

    >>> extract_relative_reference("http://localhost/fhir/Patient/test/_history/100")
    'Patient/test'

    >>> extract_relative_reference("urn:any-other-reference")
    'urn:any-other-reference'
    """
    if "/" not in reference:
        return reference

    parts = reference.split("/")
    if parts[-2] == "_history":
        return "/".join(parts[-4:-2])

    return "/".join(parts[-2:])
