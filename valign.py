import sublime
import sublime_plugin
import re

class ValignCommand(sublime_plugin.TextCommand):
	# Returns the line string for the given row.
	def get_line_string_for_row(self, row):
		view       = self.view
		text_point = view.text_point(row, 0)
		line       = view.line(text_point)
		return view.substr(line)
	
	# Expands the set of rows to all of the lines that match the current indentation level and are
	# not empty.
	def expand_rows_to_indentation(self):
		view          = self.view
		current_row   = self.start_row
		rows          = self.rows
		line_count, _ = self.view.rowcol(self.view.size())
		indentation   = -1
		
		# Expand upward and then downward from the selection.
		for direction in [-1, 1]:
			while current_row >= 0 and current_row < line_count + 1:
				line_string = self.get_line_string_for_row(current_row)
				
				# Stop at empty lines.
				if len(line_string.strip()) == 0: break
				
				# Calculate the current indentation level.
				match               = re.search("^\s+", line_string)
				indentation_string  = match.group(0) if match else None
				current_indentation = len(indentation_string) if indentation_string else 0
				
				if self.use_spaces: current_indentation /= self.tab_size
				
				# Append or prepend rows and break when we hit inconsistent indentation.
				if indentation == -1:
					indentation = current_indentation
				elif current_indentation != indentation:
					break
				else:
					if direction is -1:
						rows.insert(0, current_row)
					else:
						rows.append(current_row)
				
				# Move on to the next row.
				current_row += direction
			
			# Reset the current row for moving downward.
			current_row = rows[len(rows) - 1] + 1
	
	# Returns the character to align on based on the start row. Returns None if no proper character
	# is found.
	def calculate_alignment_character(self):
		line_string         = self.get_line_string_for_row(self.start_row)
		self.alignment_char = None
		
		for alignment_char in self.alignment_chars:
			if re.search("\\" + alignment_char["char"], line_string):
				self.alignment_char = alignment_char
				break
	
	# Adjusts the current alignment range based on the alignment character so that the range
	# contains only rows that contain the alignment character.
	def adjust_rows_for_alignment_character(self):
		rows           = self.rows
		adjusted_rows  = []
		alignment_char = self.alignment_char
		start_i        = i = rows.index(self.start_row)
		
		# Check upward and then downward from the start row.
		for direction in [-1, 1]:
			while i >= 0 and i < len(rows):
				row         = rows[i]
				line_string = self.get_line_string_for_row(row)
				
				# Make sure the character exists on this line.
				if alignment_char == None:
					if not re.search("\S+\s+\S+", line_string): break
				else:
					if not re.search("\\" + alignment_char["char"], line_string): break
				
				# Add the row.
				if direction == -1:
					adjusted_rows.insert(0, row)
				else:
					adjusted_rows.append(row)
				
				# Move on to the next row.
				i += direction
			
			# Reset i.
			i = start_i + 1
		
		# Set the new adjusted rows.
		self.rows = adjusted_rows
	
	# Normalizes the rows, creating a consistent format for alignment.
	def normalize_rows(self, edit):
		view           = self.view
		alignment_char = self.alignment_char
		
		for row in self.rows:
			line_string     = self.get_line_string_for_row(row)
			replace_pattern = ""
			replace_string  = ""
			
			if alignment_char == None:
				replace_pattern = "(?<=\S)\s+"
				replace_string  = " "
			else:
				replace_pattern = "\s*\\" + alignment_char["char"] + "\s*"
				if alignment_char["left_space"]: replace_string += " "
				
				for prefix in alignment_char["prefixes"]:
					if re.search("\\" + prefix + "\\" + alignment_char["char"], line_string):
						replace_pattern = "\s*\\" + prefix + alignment_char["char"] + "\s*"
						replace_string += prefix
						break
				
				replace_string += alignment_char["char"]
				if alignment_char["right_space"]: replace_string += " "
				
			
			match       = re.search(replace_pattern, line_string)
			column_span = match.span()
			text_point  = view.text_point(row, 0)
			view.replace(edit, sublime.Region(text_point + column_span[0], text_point + column_span[1]), replace_string)
	
	# Aligns all the rows after they've been calculated.
	def align_rows(self, edit):
		view           = self.view
		rows           = self.rows
		alignment_char = self.alignment_char
		char_indexes   = []
		max_char_index = None
		
		# Gather all of the character indexes.
		for row in rows:
			line_string = self.get_line_string_for_row(row)
			index       = 0
			has_prefix  = False
			
			if alignment_char == None:
				index = re.search("\S\s", line_string).start() + 1
			else:
				index = re.search("\\" + alignment_char["char"], line_string).start()
				
				for prefix in alignment_char["prefixes"]:
					if line_string[index - 1] == prefix:
						index     -= 1
						has_prefix = True
						break
				
				if alignment_char["alignment"] == "left": index += 1
			
			char_index = { "index": index, "has_prefix": has_prefix }
			char_indexes.append(char_index)
			
			if not max_char_index or index > max_char_index["index"]: max_char_index = char_index
		
		# Do the alignment!
		for i in range(len(rows)):
			row                 = rows[i]
			char_index          = char_indexes[i]
			extra_spaces_needed = max_char_index["index"] - char_index["index"]
			line_string         = self.get_line_string_for_row(row)
			
			if char_index["has_prefix"]:
				if not max_char_index["has_prefix"]: extra_spaces_needed -= 1
			else:
				if max_char_index["has_prefix"]: extra_spaces_needed += 1
			
			view.insert(edit, view.text_point(row, 0) + char_index["index"], " " * extra_spaces_needed)
	
	# Runs the command.
	def run(self, edit):
		view      = self.view
		selection = self.selection = view.sel()
		settings  = self.settings  = view.settings()
		lines     = self.lines     = view.lines(selection[0])
		
		# We don't align multi-selections yet.
		if len(selection) != 1: return
		
		# Store some useful stuff.
		self.lines           = view.lines(selection[0])
		self.start_row       = view.rowcol(self.lines[0].a)[0]
		self.tab_size        = int(settings.get("tab_size", 8))
		self.use_spaces      = settings.get("translate_tabs_to_spaces")
		self.alignment_chars = settings.get("alignment_chars")
		self.align_words     = settings.get("align_words")
		
		# Bail if our start row is empty.
		if len(self.get_line_string_for_row(self.start_row).strip()) == 0: return
		
		# Calculate the rows that will be affected by the alignment.
		self.rows = [self.start_row]
		self.expand_rows_to_indentation()
		self.calculate_alignment_character()
		self.adjust_rows_for_alignment_character()
		
		# Bail if we have no alignment character and we don't align words.
		if self.alignment_char is None and not self.align_words: return
		
		# Normalize the rows to get consistent formatting for alignment.
		self.normalize_rows(edit)
		
		# If we have valid rows, align them.
		if len(self.rows) > 0: self.align_rows(edit)
