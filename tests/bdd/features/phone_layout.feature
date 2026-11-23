@bdd
Feature: CollabHub on a phone

  Below 768px the sidebar is a drawer behind ☰, and a thread covers the channel
  until Back returns to it, where it was left. The drawer's rules, the panels and
  crossing the breakpoint are proven lower down.

  Background:
    Given Ada is signed in

  # Ada is on a 390 by 844 phone with touch; Grace is on a desktop.
  Scenario: On a phone, Ada picks a channel from the drawer, replies in a thread and goes Back
    Given Ada has created a public channel named "general"
    And Ada has created a public channel named "random"
    And Grace has sent 10 messages in "general"
    And Grace has sent "lunch at noon?" in "general"
    And Grace has sent 15 messages in "general"
    When Ada opens the "general" channel
    Then Ada is looking at the "general" channel
    When Ada reacts to "lunch at noon?" with "tada"
    Then Grace sees "lunch at noon?" with 1 "tada" reaction
    When Ada replies "count me in" in the thread on "lunch at noon?"
    Then Grace sees 1 reply on "lunch at noon?" without reloading
    When Ada goes Back
    Then Ada sees the "general" channel where she left it
    When Ada visits every screen at 360 wide
    Then none of them scrolls sideways
