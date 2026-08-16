@bdd
Feature: Messages

  A channel is somewhere people talk, so the messages are the point of it.
  Anyone who can see a channel can read what has been said in it and say
  something themselves — seeing the channel is enough, and nobody has to be
  added to it first. What you type is sent when you send it, and the box you
  typed it in is empty again afterwards, ready for the next thing.

  Every message shows who wrote it and when they wrote it, so a conversation
  can be followed by people who were not watching it happen. The newest
  messages are the ones you see when you open a channel; older ones are still
  there, and they load as you scroll back up through the history.

  A message has to say something — one that is empty, or nothing but spaces, is
  not sent, and neither is one longer than 8000 characters. In both cases the
  person is told which rule they broke and nothing is added to the channel.

  What you said, you can change or take back. The person who wrote a message
  can edit it or delete it, and a channel's admin can delete anything said in
  their channel — but nobody except the author ever rewrites it. An edited
  message says that it has been edited, and a deleted one leaves a note in its
  place rather than a gap, so the conversation around it still makes sense.
  Reloading does not bring the deleted words back.

  A message waits in its channel for whoever opens it next, whether or not they
  were watching when it was sent, so somebody arriving later reads the
  conversation as it happened.

  Background:
    Given Ada is signed in

  Scenario: Ada sends a message and sees it in the channel
    Given Ada has created a public channel named "general"
    When Ada sends "morning all"
    Then Ada sees "morning all" in the channel
    And Ada's message box is empty

  Scenario: A message shows its author and timestamp
    Given Ada has created a public channel named "general"
    When Ada sends "the eagle has landed"
    Then Ada sees "the eagle has landed" written by Ada
    And Ada sees "the eagle has landed" with the time it was sent

  Scenario: A blank message is not sent
    Given Ada has created a public channel named "general"
    When Ada tries to send a message that is nothing but spaces
    Then Ada is told a message cannot be empty
    And Ada sees no messages in the channel

  Scenario: A message over 8000 characters is rejected
    Given Ada has created a public channel named "general"
    When Ada tries to send a message of 8001 characters
    Then Ada is told the message is too long
    And Ada sees no messages in the channel

  Scenario: Scrolling up loads older messages
    Given Ada has created a public channel named "general"
    And "general" already holds 60 earlier messages
    When Ada reloads CollabHub
    And Ada opens the "general" channel
    Then Ada does not see the oldest message in "general"
    When Ada scrolls to the top of the history
    Then Ada sees the oldest message in "general"
    And Ada sees all 60 messages in "general"

  # Grace arrives after the message was sent, and has never joined "general" —
  # being able to see the channel is enough to read it. What she loads is the
  # history, which is a rule live delivery never replaces.
  Scenario: Grace sees Ada's message after reloading
    Given Ada has created a public channel named "general"
    And Ada has sent "the eagle has landed" in "general"
    When Grace opens CollabHub
    And Grace opens the "general" channel
    Then Grace sees "the eagle has landed" in the channel
    And Grace sees "the eagle has landed" written by Ada

  Scenario: Ada edits her own message and it shows an edited marker
    Given Ada has created a public channel named "general"
    And Ada has sent "the eagle has landed" in "general"
    When Ada edits "the eagle has landed" to say "the eagle has landed safely"
    Then Ada sees "the eagle has landed safely" in the channel
    And Ada sees "the eagle has landed safely" marked as edited

  # Grace has never joined "general" and does not need to. Ada reloads before
  # opening it: her window was already sitting in the channel, and loading it
  # afresh is what puts Grace's message in front of her.
  Scenario: Ada cannot edit Grace's message
    Given Ada has created a public channel named "general"
    And Grace has sent "shipping this afternoon" in "general"
    When Ada reloads CollabHub
    And Ada opens the "general" channel
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
    When Ada reloads CollabHub
    And Ada opens the "general" channel
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
