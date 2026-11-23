@bdd
Feature: Message actions

  Everything you can do to a message — react, reply in a thread, edit, delete —
  is behind one "⋯" button that is always there, so a touch screen with no hover
  can do all of it. The menu offers only what that message allows.

  Background:
    Given Ada is signed in

  # Touch and no hover, through to Grace's window; the rules are proven in Vitest.
  Scenario: On a touch screen, Ada reacts to Grace's message and replies in its thread
    Given Ada has created a public channel named "general"
    And Grace has sent "lunch at noon?" in "general"
    When Ada reacts to "lunch at noon?" with "tada"
    Then Grace sees "lunch at noon?" with 1 "tada" reaction
    When Ada replies "count me in" in the thread on "lunch at noon?"
    Then Grace sees 1 reply on "lunch at noon?" without reloading
