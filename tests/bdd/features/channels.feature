@bdd
Feature: Channels

  Conversation in CollabHub happens in channels. A channel belongs to exactly one
  workspace, and a public channel is visible to everyone in that workspace
  whether or not they have joined it — joining gates reading the messages, not
  knowing the channel is there. A private channel is the other way round: only
  the people in it know it is there at all.

  A channel name is something people type, say out loud and put in a URL: 3 to 80
  characters, letters, numbers and hyphens only, starting with a letter. Names
  are unique among the public channels in a workspace and case does not make two
  names different, so two people cannot both own #general — though the name is
  kept as it was typed. Whoever creates a channel administers it, and an admin
  can rename it — the new name follows it everywhere, for everyone — or archive
  it, which puts it away and takes it out of the list for good.

  Background:
    Given Ada is signed in

  @smoke
  Scenario: Ada signs in and sees her workspace
    Then Ada sees the "CollabHub Demo" workspace

  Scenario Outline: Ada creates a public channel and lands in it
    When Ada creates a public channel named "<name>"
    Then Ada is looking at the "<name>" channel
    And "<name>" is in Ada's channel list

    Examples:
      | name          |
      | general       |

  Scenario: A new public channel appears for another member
    Given Ada has created a public channel named "general"
    When Grace opens CollabHub
    Then "general" is in Grace's channel list

  Scenario: Ada creates a private channel and only she can see it
    Given Ada has created a private channel named "launch-plans"
    When Grace opens CollabHub
    Then "launch-plans" is not in Grace's channel list
    But "launch-plans" is in Ada's channel list
