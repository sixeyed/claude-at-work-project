@bdd
Feature: Channels

  # --- appended by Slice 2 ---

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
