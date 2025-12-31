-- Remove NSFW restrictions - this is a personal system
-- Keep the is_nsfw column for informational purposes only

-- Update the comment to clarify this is for categorization, not restriction
COMMENT ON COLUMN semantic_actions.is_nsfw IS 'Informational flag for mature content - no restrictions applied';

-- No structural changes needed, just update the interpretation
-- The is_nsfw flag remains for UI labeling purposes only