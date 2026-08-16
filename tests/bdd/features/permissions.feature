@bdd
Feature: Permissions

  Who can see a channel and who can change it are two different questions. A
  public channel belongs to the whole workspace; a private channel belongs to
  the people in it, and to everyone else it simply is not there. That last part
  is stricter than it sounds: following a link to a private channel looks
  exactly like following a link to a channel that never existed, because saying
  "you may not open this" would already give away that there is something to
  open.

  Changing a channel is narrower still. Renaming it, archiving it and deciding
  who is in it are a channel admin's to do, and the admin a channel starts with
  is whoever created it. Everyone else is an ordinary member, and the app does
  not offer them controls they are not allowed to use.

  Background:
    Given Ada is signed in

  @pending @s2
  Scenario: A member without admin rights is not offered the channel controls
    Given Ada has created a public channel named "general"
    When Grace opens CollabHub
    And Grace opens the "general" channel
    Then Grace is not offered the channel controls
    But Ada is offered the channel controls

  @pending @s2
  Scenario: An admin adds a member to a private channel and they can see it
    Given Ada has created a private channel named "launch-plans"
    And Ada has added Grace to the channel
    When Grace opens CollabHub
    Then "launch-plans" is in Grace's channel list
    When Grace opens the "launch-plans" channel
    Then Grace is looking at the "launch-plans" channel

  @pending @s2
  Scenario: Removing a member revokes their view of the private channel
    Given Ada has created a private channel named "launch-plans"
    And Ada has added Grace to the channel
    And Ada has removed Grace from the channel
    When Grace opens CollabHub
    Then "launch-plans" is not in Grace's channel list

  @pending @s2
  Scenario: A non-member cannot open a private channel by its URL
    Given Ada has created a private channel named "launch-plans"
    When Grace opens the link to that channel
    Then Grace is told the channel does not exist
    And "launch-plans" is not in Grace's channel list
