@bdd
Feature: Real-time delivery

  # --- appended by Slice 6 ---

  Scenario: A typing indicator appears for Grace and clears when Ada stops
    Given Ada has created a public channel named "general"
    And Grace is looking at the "general" channel
    When Ada types "standup at" into her message box without sending it
    Then Grace sees that Ada is typing
    When Ada stops typing
    Then the typing indicator clears for Grace

  Scenario: A sent message appears immediately and is confirmed
    Given Ada has created a public channel named "general"
    When Ada sends "shipping the socket writer"
    Then Ada sees "shipping the socket writer" in the channel before it is confirmed
    And Ada's message box is empty
    And "shipping the socket writer" is confirmed for Ada
    And "shipping the socket writer" appears in Ada's channel exactly once

  Scenario: A rejected send is rolled back and the error is shown
    Given Ada has created a public channel named "general"
    When Ada tries to send a message of 8001 characters
    Then Ada is told the message is too long
    And Ada sees no messages in the channel
    And Ada's message box still holds what she typed
