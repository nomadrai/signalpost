# Identity resolution

The Norwegian organisation number is the stable key. Site and profile candidates are never evidence by themselves.

## Candidate order

1. Use the registry website field.
2. When `--discover-websites` is explicitly enabled, derive conservative `.no` and `.com` host candidates from the legal name after removing legal-form suffixes and normalizing Norwegian characters. These remain candidates until independently verified.
3. Use an approved search API only when configured and within its budget. Search output is transient candidate input.
4. Use a leader-to-brand relationship only as a candidate bridge; publish only after the candidate site independently resolves to the same entity.

## Publication gate

A fetched candidate must pass the public URL safety checks and be compared with the registry identity. The strongest proof is the exact organisation number on the page, including normalized spaces, dots, and VAT suffix forms. Otherwise require the legal name plus independent address, postcode/city, phone, or registered-leader corroboration. Name similarity alone is not enough.

Reject directories, registries, marketplaces, social hosts, parked domains, generic link pages, parent pages, sister companies, franchises, and group pages listing another organisation number as the official site. Retain these as rejected candidate records when useful, but do not merge their facts into the company profile.

Social profiles are published only when they are declared by a verified company-owned page. Restricted platforms are not fetched by the product. A page with a conflicting organisation number is `ambiguous`, not a match.

## Evidence

The accepted identity tier, matched proof, candidate URL, final URL, redirect chain, content hash, retrieval time, and extraction method are retained with the website evidence. A publication is blocked when any of those pieces is absent.
