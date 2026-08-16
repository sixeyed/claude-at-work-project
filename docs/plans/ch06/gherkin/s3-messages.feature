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

  For now, a message reaches other people's windows when they next load
  CollabHub. Seeing it arrive without reloading comes later.

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
    Then "the eagle has landed" is shown as Ada's message
    And "the eagle has landed" is shown with the time it was sent

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
    When Ada opens the "general" channel
    Then Ada does not see the oldest message in "general"
    When Ada scrolls to the top of the history
    Then Ada sees the oldest message in "general"
    And Ada sees all 60 messages in "general"

  # Reloading is the behaviour under test, not a workaround: nothing delivers a
  # message to a window that is already open until live delivery arrives. Grace
  # has never joined "general" and does not need to.
  Scenario: Grace sees Ada's message after reloading
    Given Ada has created a public channel named "general"
    And Ada has sent "the eagle has landed" in "general"
    When Grace opens CollabHub
    And Grace opens the "general" channel
    Then Grace sees "the eagle has landed" in the channel
