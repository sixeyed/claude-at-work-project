@bdd
Feature: Messages

  # --- appended by Slice 4 ---

  Scenario: Ada edits her own message and it shows an edited marker
    Given Ada has created a public channel named "general"
    And Ada has sent "the eagle has landed" in "general"
    When Ada edits "the eagle has landed" to say "the eagle has landed safely"
    Then Ada sees "the eagle has landed safely" in the channel
    And "the eagle has landed safely" is marked as edited

  # Grace has never joined "general" and does not need to. Ada opens the channel
  # after Grace has posted, because nothing yet delivers a message to a window
  # that is already open.
  Scenario: Ada cannot edit Grace's message
    Given Ada has created a public channel named "general"
    And Grace has sent "shipping this afternoon" in "general"
    When Ada opens the "general" channel
    Then Ada sees "shipping this afternoon" in the channel
    And Ada has no way to edit "shipping this afternoon"

  Scenario: Ada deletes her own message and a tombstone remains after reload
    Given Ada has created a public channel named "general"
    And Ada has sent "wrong channel, sorry" in "general"
    When Ada deletes "wrong channel, sorry"
    Then Ada sees a deleted message in the channel
    And Ada does not see "wrong channel, sorry" in the channel
    When Ada reloads CollabHub
    And Ada opens the "general" channel
    Then Ada sees a deleted message in the channel
    And Ada does not see "wrong channel, sorry" in the channel

  Scenario: A channel admin deletes another user's message
    Given Ada has created a public channel named "general"
    And Grace has sent "buy my newsletter" in "general"
    When Ada opens the "general" channel
    And Ada deletes "buy my newsletter"
    Then Ada sees a deleted message in the channel
    And Ada does not see "buy my newsletter" in the channel

  Scenario: A non-admin cannot delete someone else's message
    Given Ada has created a public channel named "general"
    And Ada has sent "the eagle has landed" in "general"
    When Grace opens CollabHub
    And Grace opens the "general" channel
    Then Grace sees "the eagle has landed" in the channel
    And Grace has no way to delete "the eagle has landed"
