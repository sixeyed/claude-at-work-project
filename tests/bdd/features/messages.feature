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
