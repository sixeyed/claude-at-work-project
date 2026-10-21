@bdd
Feature: Display names

  Everyone in CollabHub goes by a name of their own choosing, and no two people
  share one, so a name on a message always means one person. Changing yours is
  something you do once, on Settings; your own screen shows it straight away,
  and everyone else sees it the next time their view of the workspace is fetched.

  Background:
    Given Ada is signed in

  Scenario: Grace sees the name Alan chose on his message
    Given Ada has created a public channel named "general"
    And Alan has sent "the kettle is on" in "general"
    When Alan changes his display name to "Alan Turing" in Settings
    Then Alan sees "Alan Turing" as his name
    When Grace opens CollabHub
    And Grace opens the "general" channel
    Then Grace sees "the kettle is on" written by Alan Turing
