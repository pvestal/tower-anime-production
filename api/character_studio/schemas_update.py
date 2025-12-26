# Add these fields to CharacterGenerateRequest after line 29 (after project field):

    scene: Optional[str] = Field(
        None,
        description="Scene/location (e.g., 'apartment_morning', 'office_desk')",
        max_length=100
    )
    action: Optional[str] = Field(
        None,
        description="Character action (e.g., 'yoga_practice', 'drinking_coffee')",
        max_length=100
    )
