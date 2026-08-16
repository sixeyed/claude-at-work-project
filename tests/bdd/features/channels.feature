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
      | team-42       |
      | Design-Review |

  Scenario: A new public channel appears for another member
    Given Ada has created a public channel named "general"
    When Grace opens CollabHub
    Then "general" is in Grace's channel list

  Scenario Outline: A public channel name cannot be reused, whatever its case
    Given Ada has created a public channel named "general"
    When Ada tries to create a second public channel named "<name>"
    Then Ada is told that channel name is already taken
    And "general" appears in Ada's channel list exactly once

    Examples:
      | name    |
      | general |
      | General |
      | GENERAL |

  Scenario: A channel name cannot be blank
    When Ada tries to create a public channel with a blank name
    Then Ada is told a channel name is required
    And Ada's channel list is empty

  Scenario Outline: A channel name has to be one people can type
    When Ada tries to create a public channel named "<name>"
    Then Ada is told the name <complaint>
    And Ada's channel list is empty

    Examples:
      | name      | complaint                                 |
      | ab        | is too short                              |
      | 1password | must start with a letter                  |
      | -general  | must start with a letter                  |
      | dev team  | can only use letters, numbers and hyphens |
      | dev_team  | can only use letters, numbers and hyphens |
      | général   | can only use letters, numbers and hyphens |

  Scenario: A channel name cannot be longer than 80 characters
    When Ada tries to create a public channel with an 81-character name
    Then Ada is told the name is too long
    And Ada's channel list is empty

  Scenario: A channel admin renames a channel
    Given Ada has created a public channel named "general"
    When Ada renames the channel to "general-chat"
    Then Ada is looking at the "general-chat" channel
    And "general-chat" is in Ada's channel list
    But "general" is not in Ada's channel list

  Scenario: A rename is visible to everyone in the workspace
    Given Ada has created a public channel named "general"
    And Ada has renamed the channel to "general-chat"
    When Grace opens CollabHub
    Then "general-chat" is in Grace's channel list
    But "general" is not in Grace's channel list

  Scenario: An admin archives a channel and it leaves the list
    Given Ada has created a public channel named "general"
    When Ada archives the channel
    Then "general" is not in Ada's channel list

  Scenario: Ada creates a private channel and only she can see it
    Given Ada has created a private channel named "launch-plans"
    When Grace opens CollabHub
    Then "launch-plans" is not in Grace's channel list
    But "launch-plans" is in Ada's channel list
