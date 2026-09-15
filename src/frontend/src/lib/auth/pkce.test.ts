import { describe, expect, it } from 'vitest'

import { challengeFor, createVerifier } from './pkce'

describe('createVerifier', () => {
  it('is 32 random bytes as unpadded base64url', () => {
    const verifier = createVerifier()

    // 32 bytes is 43 base64url characters once the padding is gone, and
    // RFC 7636 §4.1 allows only the unreserved alphabet.
    expect(verifier).toMatch(/^[A-Za-z0-9_-]{43}$/)
  })

  it('is different every time', () => {
    expect(createVerifier()).not.toBe(createVerifier())
  })
})

describe('challengeFor', () => {
  it('matches the S256 example in RFC 7636 appendix B', async () => {
    expect(await challengeFor('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk')).toBe(
      'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM',
    )
  })
})
