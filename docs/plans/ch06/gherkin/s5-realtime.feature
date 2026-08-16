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

  Background:
    Given Ada is signed in

  Scenario: Grace sees Ada's message without reloading
    Given Ada has created a public channel named "general"
    And Grace is looking at the "general" channel
    When Ada sends "the socket layer is live"
    Then Grace sees "the socket layer is live" in the channel without reloading
    And "the socket layer is live" appears in Ada's channel exactly once

  Scenario: Ada's edit propagates to Grace live
    Given Ada has created a public channel named "general"
    And Grace is looking at the "general" channel
    And Ada has sent "standup at four"
    When Ada edits "standup at four" to "standup at five"
    Then Grace sees "standup at five" in the channel without reloading
    And Grace sees "standup at five" marked as edited
    But Grace does not see "standup at four" in the channel

  Scenario: Ada's delete propagates to Grace live
    Given Ada has created a public channel named "general"
    And Grace is looking at the "general" channel
    And Ada has sent "wrong channel, sorry"
    When Ada deletes "wrong channel, sorry"
    Then Grace sees a deleted message in the channel without reloading
    But Grace does not see "wrong channel, sorry" in the channel

  Scenario: Grace does not receive messages for a channel she is not looking at
    Given Ada has created a public channel named "random"
    And Ada has created a public channel named "general"
    And Grace is looking at the "random" channel
    When Ada sends "only for general"
    Then Grace does not see "only for general" in the channel
    And Grace sees "only for general" when she opens the "general" channel

  Scenario: The stream recovers after the connection drops
    Given Ada has created a public channel named "general"
    And Grace is looking at the "general" channel
    When Grace's network drops
    And Ada sends "sent while Grace was away"
    And Grace's network comes back
    Then Grace's connection is restored
    And Grace sees "sent while Grace was away" in the channel without reloading
