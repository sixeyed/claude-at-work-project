@bdd
Feature: Real-time delivery

  CollabHub is left open all day, so what happens in a channel has to show up in
  it while people are watching. When someone posts, edits or deletes a message,
  everyone looking at that channel sees the change land in place — no refresh and
  no re-opening the channel — including the person who made it, whose own message
  appears once and not twice. An edit rewrites the message where it stands, and a
  delete leaves the space it occupied marked as a deleted message rather than
  quietly taking the row away.

  Live updates follow the channel a person is looking at. A message posted in one
  channel does not turn up in another, and a channel someone has not opened is
  simply waiting for them, with the message in it, when they do. A connection
  that drops is not a lost conversation: when the network comes back the channel
  catches itself up on its own, including whatever was said while it was away.

  Sending is meant to feel instant. What you send shows in the channel the moment
  you send it and settles a moment later, once the server has it. If it is
  refused — for being too long, say — it is taken back out again and the words
  are handed back to the box you typed them in, so nothing is lost. And while
  somebody is typing, the other people watching that channel are told so, and the
  message stops being shown once they stop.

  Background:
    Given Ada is signed in

  Scenario: Grace sees Ada's message without reloading
    Given Ada has created a public channel named "general"
    And Grace is looking at the "general" channel
    When Ada sends "the coffee has arrived"
    Then Grace sees "the coffee has arrived" in the channel without reloading
    And "the coffee has arrived" appears in Ada's channel exactly once

  # Ada's message is in the history Grace loads, not something Grace received
  # live — so the scenario turns on the edit arriving, and nothing else.
  Scenario: Ada's edit propagates to Grace live
    Given Ada has created a public channel named "general"
    And Ada has sent "standup at four" in "general"
    And Grace is looking at the "general" channel
    When Ada edits "standup at four" to say "standup at five"
    Then Grace sees "standup at five" in the channel without reloading
    And Grace sees "standup at five" marked as edited
    But Grace does not see "standup at four" in the channel

  Scenario: Ada's delete propagates to Grace live
    Given Ada has created a public channel named "general"
    And Ada has sent "wrong channel, sorry" in "general"
    And Grace is looking at the "general" channel
    When Ada deletes "wrong channel, sorry"
    Then Grace sees a deleted message in the channel without reloading
    But Grace does not see "wrong channel, sorry" in the channel

  Scenario: Grace does not receive messages for a channel she is not looking at
    Given Ada has created a public channel named "random"
    And Ada has created a public channel named "general"
    And Grace is looking at the "random" channel
    When Ada sends "only for general" in "general"
    Then "only for general" appears in Ada's channel exactly once
    But Grace does not see "only for general" in the channel
    When Grace opens the "general" channel
    Then Grace sees "only for general" in the channel

  Scenario: The stream recovers after the connection drops
    Given Ada has created a public channel named "general"
    And Grace is looking at the "general" channel
    When Grace's network drops
    And Ada sends "sent while Grace was away"
    And Grace's network comes back
    Then Grace's connection is restored
    And Grace sees "sent while Grace was away" in the channel without reloading

  Scenario: A typing indicator appears for Grace and clears when Ada stops
    Given Ada has created a public channel named "general"
    And Grace is looking at the "general" channel
    When Ada types "standup at" into her message box without sending it
    Then Grace sees that Ada is typing
    When Ada stops typing
    Then Grace no longer sees that Ada is typing

  Scenario: A sent message appears immediately and is confirmed
    Given Ada has created a public channel named "general"
    When Ada sends "lunch is at one"
    Then Ada sees "lunch is at one" in the channel before it is confirmed
    And Ada's message box is empty
    And Ada sees "lunch is at one" confirmed
    And "lunch is at one" appears in Ada's channel exactly once

  Scenario: A rejected send is rolled back and the error is shown
    Given Ada has created a public channel named "general"
    When Ada tries to send a message of 8001 characters
    Then Ada sees that message in the channel before it is confirmed
    And Ada is told the message is too long
    And Ada sees no messages in the channel
    And Ada's message box still holds what she typed
