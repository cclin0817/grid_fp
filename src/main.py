#!/usr/bin/env python3
"""
This script provides a GUI for block placement in a grid, a task common in
chip design floorplanning. It allows users to place, move, delete, and orient
blocks, save/load placements, and use guidelines for alignment.
"""
import json
import argparse
import os
import re
import csv
import ast
import tkinter as tk
import webcolors
from copy import deepcopy
from enum import Enum
from tkinter import filedialog, messagebox, simpledialog


import log

# --- Enums for better state management ---

class Mode(Enum):
    """Defines the various operational modes of the GUI."""
    PLACE = "Place"
    DELETE = "Delete"
    DELETE_REGION = "Delete Region"
    CHANGE_ORIENTATION = "Change Orientation"
    PLACE_BLOCKAGE = "Place Blockage"
    DELETE_BLOCKAGE = "Delete Blockage"
    SELECT_WI_BLOCKAGE = "Select w/i blockage (move:w/a/s/d/t) (duplicate:c) (swap:x)"
    SELECT_WO_BLOCKAGE = "Select w/o blockage (move:w/a/s/d/t) (duplicate:c) (swap:x)"

class Orientation(Enum):
    """Defines the possible orientations of a block."""
    R0 = "R0"
    MX = "MX"
    MY = "MY"
    R180 = "R180"
    R90 = "R90"

# --- Utility Functions ---

def darken_color(color_name, darken_factor=0.7):
    """Darkens a given color by a specified factor."""
    try:
        rgb = webcolors.name_to_rgb(color_name)
        r, g, b = [int(c * darken_factor) for c in rgb]
        return webcolors.rgb_to_hex((r, g, b))
    except ValueError as e:
        log.logger.error(f"Error darkening color {color_name}: {e}")
        return color_name  # Return original color on error

def read_args():
    parser = argparse.ArgumentParser(description="Block Placement GUI")
    parser.add_argument('-p', '--project_name', default='mye', help='The name of the project to load.')
    return vars(parser.parse_args())

def read_block_config(filename):
    shapes, colors, pinsides = {}, {}, {}
    try:
        with open(filename, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                name = row['block_name']
                width, height = int(row['width']), int(row['height'])
                shapes[name] = [(dx, dy) for dy in range(height) for dx in range(width)]
                colors[name] = row['color']
                pinsides[name] = ast.literal_eval(row['pinside'])
    except FileNotFoundError:
        log.logger.error(f"Block config file not found: {filename}")
        messagebox.showerror("Error", f"Block config file not found: {filename}")
    except (KeyError, ValueError) as e:
        log.logger.error(f"Error reading block config {filename}: {e}")
        messagebox.showerror("Error", f"Error reading block config {filename}: {e}")
    return shapes, colors, pinsides

def read_project_config(filename):
    designs = []
    try:
        with open(filename, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                designs.append({
                    'design_name': row['design_name'],
                    'grid_width': int(row['grid_width']),
                    'grid_height': int(row['grid_height']),
                })
    except FileNotFoundError:
        log.logger.error(f"Project config file not found: {filename}")
        messagebox.showerror("Error", f"Project config file not found: {filename}")
    except (KeyError, ValueError) as e:
        log.logger.error(f"Error reading project config {filename}: {e}")
        messagebox.showerror("Error", f"Error reading project config {filename}: {e}")
    return designs

class CustomDirectionDialog(simpledialog.Dialog):
    def body(self, master):
        tk.Label(master, text="Select the direction for auto-repeat:").grid(row=0)
        self.var = tk.StringVar(master, "V")
        self.options = ["V", "H"]
        self.option_menu = tk.OptionMenu(master, self.var, *self.options)
        self.option_menu.grid(row=0, column=1)
        return self.option_menu

    def apply(self):
        self.result = self.var.get()

class BlockObject:
    """Represents a single block object on the canvas."""
    def __init__(self, cell_name, x, y, block_shape, orientation):
        self.data = {'cell_name': cell_name, 'shape_ids': [], 'x': x, 'y': y, 'orientation': orientation}
        self.block_shape = block_shape
        self.update_bounding_box()

    def update_location(self, x, y):
        """Updates the block's grid coordinates."""
        self.data['x'], self.data['y'] = x, y
        self.update_bounding_box()

    def update_orientation(self):
        """Cycles through the available orientations."""
        orientations = [o.value for o in Orientation]
        current_idx = orientations.index(self.data['orientation'])
        self.data['orientation'] = orientations[(current_idx + 1) % len(orientations)]
        # Note: Shape rotation logic is complex and has been omitted for now.

    def update_bounding_box(self):
        """Recalculates the coordinate bounding box of the block."""
        self.llx_in_canvas = self.data['x']
        self.lly_in_canvas = self.data['y']
        if not self.block_shape:
            self.urx_in_canvas, self.ury_in_canvas = self.llx_in_canvas, self.lly_in_canvas
            return
        self.urx_in_canvas = self.llx_in_canvas + max(dx for dx, dy in self.block_shape)
        self.ury_in_canvas = self.lly_in_canvas + max(dy for dx, dy in self.block_shape)

class BlockPlacement(tk.Tk):
    def __init__(self, project_name, design_name, grid_width, grid_height):
        super().__init__()
        self.project_name = project_name
        self.design_name = design_name
        self.grid_width = grid_width
        self.grid_height = grid_height
        
        self._init_variables()
        self._init_ui()
        self._bind_events()
        self.draw()

    def _init_variables(self):
        """Initializes all state variables for the application."""
        self.initial_cell_size = int(min(
            self.winfo_screenwidth() / (2 * self.grid_width),
            (self.winfo_screenheight() - 100) / self.grid_height
        ) * 100) / 100
        self.cell_size = self.initial_cell_size

        self.result_dir = os.path.join('output', self.project_name)
        if not os.path.exists(self.result_dir):
            os.makedirs(self.result_dir)

        csv_path = os.path.join('input', self.project_name, f'{self.project_name}_{self.design_name}.csv')
        log.logger.info(f"Reading design spec from {csv_path}")
        self.shape_definitions, self.shape_colors, self.shape_pinsides = read_block_config(csv_path)

        self.block_objects, self.selected_blocks = {}, {}
        self.guideline_block_ids, self.guideline_ids = {}, []
        self.selected_shape = None
        self.grid_state = [[None for _ in range(self.grid_height)] for _ in range(self.grid_width)]
        
        self.drag_rect_id, self.drag_start_pos, self.drag_start_grid = None, None, None

    def _init_ui(self):
        """Creates and configures the UI elements."""
        self.title(f"{self.project_name} {self.design_name} Placement GUI")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        canvas_frame = tk.Frame(self)
        canvas_frame.grid(row=0, column=0, sticky="nsew")
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        
        self.canvas_width = self.grid_width * self.cell_size
        self.canvas_height = self.grid_height * self.cell_size
        self.grid_canvas = tk.Canvas(canvas_frame, bg='white', scrollregion=(0, 0, self.canvas_width, self.canvas_height))
        self.grid_canvas.grid(row=0, column=0, sticky="nsew")

        hbar = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.grid_canvas.xview)
        hbar.grid(row=1, column=0, sticky="ew")
        vbar = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.grid_canvas.yview)
        vbar.grid(row=0, column=1, sticky="ns")
        self.grid_canvas.config(xscrollcommand=hbar.set, yscrollcommand=vbar.set)

        self.toolbar_frame = tk.Frame(self)
        self.toolbar_frame.grid(row=0, column=1, sticky="ns", padx=10, pady=10)
        
        self._create_toolbar_buttons()
        self._create_mode_radios()
        self._create_shape_buttons()

    def _create_toolbar_buttons(self):
        """Creates the main action buttons in the toolbar."""
        actions = [
            ("Fit Floorplan", self.fit_fp),
            ("Save Placement", self.save_to_file),
            ("Load Default", lambda: self.load_from_file(default=True)),
            # ("Load Specific", lambda: self.load_from_file(default=False)), # This was commented out in original
            ("Clear Floorplan", self.clear_fp)
        ]
        for text, command in actions:
            tk.Button(self.toolbar_frame, text=text, command=command).pack(pady=(0, 10), fill=tk.X)

    def _create_mode_radios(self):
        """Creates the radio buttons for mode selection."""
        self.mode = tk.StringVar(value=Mode.PLACE.value)
        self.mode_label = tk.Label(self.toolbar_frame, text=f"Mode: {self.mode.get()}")
        self.mode_label.pack(pady=(10, 5))
        
        for mode in Mode:
            tk.Radiobutton(
                self.toolbar_frame, text=mode.value, variable=self.mode, 
                value=mode.value, command=self.update_mode_label
            ).pack(anchor=tk.W)

    def _create_shape_buttons(self):
        """Creates the buttons for selecting different block shapes."""
        num_columns = 5
        container = tk.Frame(self.toolbar_frame)
        container.pack(side=tk.BOTTOM, pady=(20,0))
        
        frames = [tk.Frame(container) for _ in range(num_columns)]
        for i, frame in enumerate(frames):
            frame.grid(row=0, column=i, sticky=tk.N, padx=5)

        for i, name in enumerate(self.shape_definitions.keys()):
            shape_frame = tk.Frame(frames[i % num_columns])
            shape_frame.pack(pady=5)
            
            coords = self.shape_definitions[name]
            max_x = max(x for x, y in coords) if coords else 0
            max_y = max(y for x, y in coords) if coords else 0
            
            btn_canvas = tk.Canvas(
                shape_frame, 
                width=(max_x + 1) * self.initial_cell_size / 2,
                height=(max_y + 1) * self.initial_cell_size / 2,
                bg='white', highlightthickness=1, highlightbackground="black"
            )
            btn_canvas.shape_name = name
            btn_canvas.bind("<Button-1>", self.select_shape)
            self._draw_shape_preview(btn_canvas, name)
            btn_canvas.pack()
            tk.Label(shape_frame, text=name).pack()

    def _bind_events(self):
        """Binds keyboard and mouse events to their handlers."""
        self.bind("<Left>", lambda e: self.grid_canvas.xview_scroll(-1, "units"))
        self.bind("<Right>", lambda e: self.grid_canvas.xview_scroll(1, "units"))
        self.bind("<Up>", lambda e: self.grid_canvas.yview_scroll(-1, "units"))
        self.bind("<Down>", lambda e: self.grid_canvas.yview_scroll(1, "units"))
        self.bind("f", self.fit_fp)
        self.bind("a", self.move_left)
        self.bind("d", self.move_right)
        self.bind("s", self.move_down)
        self.bind("w", self.move_up)
        self.bind("c", self.duplicate_selected)
        self.bind("t", self.move_to_coord)
        self.bind("x", self.swap_selected)
        self.focus_set()

        self.grid_canvas.bind("<Button-1>", self.on_canvas_press)
        self.grid_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.grid_canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.grid_canvas.bind("<Button-3>", self.toggle_guideline)
        self.grid_canvas.bind("<Button-4>", lambda e: self.zoom(1.1))
        self.grid_canvas.bind("<Button-5>", lambda e: self.zoom(0.9))

    # --- Event Handlers ---
    def on_canvas_press(self, event):
        """Handles the start of a mouse action on the canvas."""
        canvas_x = self.grid_canvas.canvasx(event.x)
        canvas_y = self.grid_canvas.canvasy(event.y)
        grid_x, grid_y = int(canvas_x / self.cell_size), int(canvas_y / self.cell_size)

        if not (0 <= grid_x < self.grid_width and 0 <= grid_y < self.grid_height):
            messagebox.showwarning("Out of Bounds", "Clicked outside the grid area.")
            return

        mode = self.mode.get()
        drag_modes = [m.value for m in Mode if "Region" in m.value or "Select" in m.value or "Blockage" in m.value]

        if mode in drag_modes:
            self.drag_start_pos = (canvas_x, canvas_y)
            self.drag_start_grid = (grid_x, grid_y)
        elif mode == Mode.PLACE.value:
            self._place_block_at(grid_x, grid_y)
        elif mode == Mode.DELETE.value:
            self._delete_block_at(grid_x, grid_y)
        elif mode == Mode.CHANGE_ORIENTATION.value:
            self._change_orientation_at(grid_x, grid_y)

    def on_canvas_drag(self, event):
        """Handles mouse dragging for drawing a selection rectangle."""
        if self.drag_start_pos is None: return
        if self.drag_rect_id: self.grid_canvas.delete(self.drag_rect_id)
        
        self.drag_rect_id = self.grid_canvas.create_rectangle(
            self.drag_start_pos[0], self.drag_start_pos[1], 
            self.grid_canvas.canvasx(event.x), self.grid_canvas.canvasy(event.y),
            outline='blue', dash=(4, 2)
        )

    def on_canvas_release(self, event):
        """Handles the end of a mouse action, completing a drag operation."""
        if self.drag_rect_id: self.grid_canvas.delete(self.drag_rect_id)
        if self.drag_start_pos is None: return

        x_start, y_start = self.drag_start_grid
        x_end, y_end = int(self.grid_canvas.canvasx(event.x) / self.cell_size), int(self.grid_canvas.canvasy(event.y) / self.cell_size)
        
        region = (min(x_start, x_end), min(y_start, y_end), max(x_start, x_end), max(y_start, y_end))
        
        mode_actions = {
            Mode.PLACE_BLOCKAGE.value: lambda: self._place_blockage_in_region(*region),
            Mode.DELETE_REGION.value: lambda: self._delete_blocks_in_region(*region, all_types=True),
            Mode.DELETE_BLOCKAGE.value: lambda: self._delete_blocks_in_region(*region, all_types=False),
            Mode.SELECT_WI_BLOCKAGE.value: lambda: self._select_blocks_in_region(*region, with_blockage=True),
            Mode.SELECT_WO_BLOCKAGE.value: lambda: self._select_blocks_in_region(*region, with_blockage=False),
        }
        
        action = mode_actions.get(self.mode.get())
        if action: action()

        self.drag_start_pos = self.drag_rect_id = self.drag_start_grid = None
        self.draw()

    # --- Action Methods ---
    def _place_block_at(self, x, y):
        if not self.selected_shape: return
        if not self._is_location_legal(x, y, self.selected_shape, show_warning=True): return
        
        block = BlockObject(self.selected_shape, x, y, self.shape_definitions[self.selected_shape], 'R0')
        self.block_objects[id(block)] = block
        self.draw()

    def _delete_block_at(self, x, y):
        block_id = self.grid_state[x][y]
        if block_id is None:
            messagebox.showwarning("Invalid Deletion", "No object at the specified location.")
            return
        self._remove_block_by_id(block_id)
        self.draw()

    def _change_orientation_at(self, x, y):
        block_id = self.grid_state[x][y]
        if block_id is None:
            messagebox.showwarning("Invalid Operation", "No object at the specified location.")
            return
        
        block = self.block_objects[block_id]
        block.update_orientation()
        # Redrawing will handle visual update. Legality checks for rotation are complex
        # and were not fully implemented in the original code.
        self.draw()

    def _place_blockage_in_region(self, x1, y1, x2, y2):
        for x in range(x1, x2 + 1):
            for y in range(y1, y2 + 1):
                if self._is_location_legal(x, y, 'Blockage', show_warning=False):
                    block = BlockObject('Blockage', x, y, self.shape_definitions['Blockage'], 'R0')
                    self.block_objects[id(block)] = block

    def _delete_blocks_in_region(self, x1, y1, x2, y2, all_types):
        ids_to_delete = set()
        for x in range(x1, x2 + 1):
            for y in range(y1, y2 + 1):
                if not (0 <= x < self.grid_width and 0 <= y < self.grid_height): continue
                block_id = self.grid_state[x][y]
                if block_id and (all_types or self.block_objects[block_id].data['cell_name'] == 'Blockage'):
                    ids_to_delete.add(block_id)
        for block_id in ids_to_delete:
            self._remove_block_by_id(block_id)

    def _select_blocks_in_region(self, x1, y1, x2, y2, with_blockage):
        self.selected_blocks.clear()
        for x in range(x1, x2 + 1):
            for y in range(y1, y2 + 1):
                if not (0 <= x < self.grid_width and 0 <= y < self.grid_height): continue
                block_id = self.grid_state[x][y]
                if block_id:
                    block = self.block_objects[block_id]
                    if with_blockage or block.data['cell_name'] != 'Blockage':
                        self.selected_blocks[block] = True
        log.logger.info(f"Selected {len(self.selected_blocks)} blocks.")

    def _remove_block_by_id(self, block_id):
        if block_id in self.block_objects:
            del self.block_objects[block_id]
        if block_id in self.guideline_block_ids:
            del self.guideline_block_ids[block_id]
        if block_id in self.selected_blocks:
            del self.selected_blocks[block_id]

    # --- Drawing ---
    def draw(self):
        """Redraws the entire canvas, including grid and all blocks."""
        self.grid_canvas.delete("all")
        self._draw_grid()
        
        self.grid_state = [[None for _ in range(self.grid_height)] for _ in range(self.grid_width)]
        
        # Draw non-blockage items first, then blockages to ensure text visibility
        sorted_blocks = sorted(self.block_objects.values(), key=lambda b: b.data['cell_name'] == 'Blockage')
        for block in sorted_blocks:
            self._draw_block(block)
        self._draw_guidelines()

    def _draw_grid(self):
        """Draws the grid lines on the canvas."""
        # Thin lines for every cell
        for i in range(self.grid_width + 1):
            self.grid_canvas.create_line(i * self.cell_size, 0, i * self.cell_size, self.canvas_height, fill='lightgray', width=0.1)
        for j in range(self.grid_height + 1):
            self.grid_canvas.create_line(0, j * self.cell_size, self.canvas_width, j * self.cell_size, fill='lightgray', width=0.1)
        
        # Thicker lines for intervals
        interval = 10 if self.cell_size > 5 else 20
        color = "red" if self.cell_size > 5 else "gray"
        for i in range(0, self.grid_width, interval):
            self.grid_canvas.create_line(i*self.cell_size, 0, i*self.cell_size, self.canvas_height, fill=color, width=0.1)
        for j in range(0, self.grid_height, interval):
            self.grid_canvas.create_line(0, j*self.cell_size, self.canvas_width, j*self.cell_size, fill=color, width=0.1)

    def _draw_block(self, block):
        """Draws a single block, its text, and pin indicators."""
        color = self.shape_colors.get(block.data['cell_name'], 'gray')
        if block in self.selected_blocks:
            color = darken_color(color, 0.5)

        llx, lly = block.llx_in_canvas * self.cell_size, block.lly_in_canvas * self.cell_size
        urx, ury = (block.urx_in_canvas + 1) * self.cell_size, (block.ury_in_canvas + 1) * self.cell_size
        
        if block.data['cell_name'] == "TSV":
            shape_id = self.grid_canvas.create_oval(llx, lly, urx, ury, fill=color, outline='')
        else:
            shape_id = self.grid_canvas.create_rectangle(llx, lly, urx, ury, fill=color, outline='')
        block.data['shape_ids'] = [shape_id]

        for dx, dy in block.block_shape:
            grid_x, grid_y = block.data['x'] + dx, block.data['y'] + dy
            if 0 <= grid_x < self.grid_width and 0 <= grid_y < self.grid_height:
                self.grid_state[grid_x][grid_y] = id(block)
        
        self._draw_block_text(block, (llx + urx) / 2, (lly + ury) / 2)
        self._draw_block_pins(block, llx, lly, urx, ury)

    def _draw_block_text(self, block, center_x, center_y):
        """Draws the name and orientation text on a block."""
        name = block.data['cell_name']
        if name in ['Blockage', 'GPIO']: return

        # Shorten common prefixes
        for prefix in ["FCCC_ARRAY_", "CPU_LITE_ARRAY_", "CPU2_ARRAY_", "SRAM_ARRAY_", "ISP_ARRAY_"]:
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        else:
            name = name.split('_')[0]

        block.data['shape_ids'].append(self.grid_canvas.create_text(center_x, center_y - 10, text=name, font=("Arial", 8)))
        block.data['shape_ids'].append(self.grid_canvas.create_text(center_x, center_y + 10, text=block.data['orientation'], font=("Arial", 8)))

    def _draw_block_pins(self, block, llx, lly, urx, ury):
        """Draws lines on the block's border to indicate pin sides."""
        pin_sides = self.shape_pinsides.get(block.data['cell_name'], "")
        orientation = block.data['orientation']
        width = 3
        
        pin_map = {
            'R0':   {'T': 'T', 'B': 'B', 'L': 'L', 'R': 'R'}, 'MX': {'T': 'B', 'B': 'T', 'L': 'L', 'R': 'R'},
            'MY':   {'T': 'T', 'B': 'B', 'L': 'R', 'R': 'L'}, 'R180': {'T': 'B', 'B': 'T', 'L': 'R', 'R': 'L'},
            'R90':  {'T': 'L', 'B': 'R', 'L': 'B', 'R': 'T'}
        }
        
        if orientation not in pin_map: return

        for side in pin_sides:
            oriented_side = pin_map[orientation].get(side)
            if oriented_side == 'T': line_id = self.grid_canvas.create_line(llx, lly, urx, lly, width=width)
            elif oriented_side == 'B': line_id = self.grid_canvas.create_line(llx, ury, urx, ury, width=width)
            elif oriented_side == 'L': line_id = self.grid_canvas.create_line(llx, lly, llx, ury, width=width)
            elif oriented_side == 'R': line_id = self.grid_canvas.create_line(urx, lly, urx, ury, width=width)
            else: continue
            block.data['shape_ids'].append(line_id)

    def _draw_guidelines(self):
        """Draws alignment guidelines for selected blocks."""
        for line_id in self.guideline_ids: self.grid_canvas.delete(line_id)
        self.guideline_ids.clear()
        
        for block_id in self.guideline_block_ids:
            if block_id not in self.block_objects: continue
            block = self.block_objects[block_id]
            llx, lly = block.llx_in_canvas * self.cell_size, block.lly_in_canvas * self.cell_size
            urx, ury = (block.urx_in_canvas + 1) * self.cell_size, (block.ury_in_canvas + 1) * self.cell_size
            
            self.guideline_ids.append(self.grid_canvas.create_line(llx, 0, llx, self.canvas_height, fill="purple", width=2))
            self.guideline_ids.append(self.grid_canvas.create_line(urx, 0, urx, self.canvas_height, fill="purple", width=2))
            self.guideline_ids.append(self.grid_canvas.create_line(0, lly, self.canvas_width, lly, fill="purple", width=2))
            self.guideline_ids.append(self.grid_canvas.create_line(0, ury, self.canvas_width, ury, fill="purple", width=2))

    def _draw_shape_preview(self, canvas, shape_name):
        """Draws a miniature preview of a shape on its selection button."""
        color = self.shape_colors.get(shape_name, 'gray')
        preview_cell_size = self.initial_cell_size / 2
        for x, y in self.shape_definitions.get(shape_name, []):
            canvas.create_rectangle(
                x * preview_cell_size, y * preview_cell_size,
                (x + 1) * preview_cell_size, (y + 1) * preview_cell_size,
                fill=color, outline=''
            )

    # --- Helpers & Callbacks ---
    def update_mode_label(self):
        self.mode_label.config(text=f"Mode: {self.mode.get()}")

    def select_shape(self, event):
        self.selected_shape = event.widget.shape_name
        messagebox.showinfo("Shape Selected", f"Selected shape: {self.selected_shape}")

    def zoom(self, factor):
        """Zooms the canvas in or out by a given factor."""
        new_size = self.cell_size * factor
        if new_size < 1: return # Prevent zooming out too far
        self.cell_size = new_size
        self.canvas_width = self.grid_width * self.cell_size
        self.canvas_height = self.grid_height * self.cell_size
        self.grid_canvas.config(scrollregion=(0, 0, self.canvas_width, self.canvas_height))
        self.draw()

    def fit_fp(self, event=None):
        """Resets the zoom to fit the entire floorplan."""
        self.cell_size = self.initial_cell_size
        self.canvas_width = self.grid_width * self.cell_size
        self.canvas_height = self.grid_height * self.cell_size
        self.grid_canvas.config(scrollregion=(0, 0, self.canvas_width, self.canvas_height))
        self.draw()

    def toggle_guideline(self, event):
        """Toggles guidelines for the block under the cursor."""
        x, y = int(self.grid_canvas.canvasx(event.x) / self.cell_size), int(self.grid_canvas.canvasy(event.y) / self.cell_size)
        if not (0 <= x < self.grid_width and 0 <= y < self.grid_height): return
        block_id = self.grid_state[x][y]
        if block_id is None: return
        
        if block_id in self.guideline_block_ids:
            del self.guideline_block_ids[block_id]
        else:
            self.guideline_block_ids[block_id] = True
        self.draw()

    def _is_location_legal(self, x, y, shape_name, show_warning=False, ignore_block_id=None):
        """Checks if a shape can be placed at a given location."""
        for dx, dy in self.shape_definitions.get(shape_name, []):
            gx, gy = x + dx, y + dy
            if not (0 <= gx < self.grid_width and 0 <= gy < self.grid_height):
                if show_warning: messagebox.showwarning("Invalid Placement", "Cannot place shape here: Out of bounds.")
                return False
            
            occupying_id = self.grid_state[gx][gy]
            if occupying_id is not None and occupying_id != ignore_block_id:
                if show_warning: messagebox.showwarning("Invalid Placement", "Cannot place shape here: Space is already occupied.")
                return False
        return True

    # --- File Operations ---
    def save_to_file(self):
        """Saves the current placement to a JSON file."""
        filename = os.path.join(self.result_dir, f"{self.design_name}_placement.json")
        if os.path.exists(filename) and not messagebox.askyesno("Overwrite?", f"File '{filename}' exists. Overwrite?"):
            return
        
        with open(filename, "w") as f:
            json.dump({id(b): b.data for b in self.block_objects.values()}, f, indent=4)
        messagebox.showinfo("Save Successful", f"Placement saved to {filename}")
        self._save_grid_txt()

    def _save_grid_txt(self):
        """Saves a text representation of the grid."""
        filename = os.path.join(self.result_dir, f"{self.design_name}_grid.txt")
        with open(filename, "w") as f:
            for y in range(self.grid_height):
                row = []
                for x in range(self.grid_width):
                    block_id = self.grid_state[x][y]
                    if block_id:
                        block = self.block_objects[block_id]
                        row.append(f"{block.data['cell_name']}({id(block)})({block.data['orientation']})")
                    else:
                        row.append("None")
                f.write(" , ".join(row) + '\n')

    def load_from_file(self, default):
        """Loads a placement from a JSON file."""
        if default:
            filename = os.path.join(self.result_dir, f"{self.design_name}_placement.json")
        else:
            filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])

        if not filename or not os.path.exists(filename):
            if default:
                messagebox.showwarning("Load Error", f"Default placement file not found: {filename}")
            return

        try:
            with open(filename, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            messagebox.showerror("Load Error", f"Failed to load file {filename}: {e}")
            return
        
        self.clear_fp(confirm=False)
        for block_data in data.values():
            name = block_data['cell_name']
            if name not in self.shape_definitions:
                log.logger.warning(f"Skipping unknown block type '{name}' from placement file.")
                continue
            block = BlockObject(name, block_data['x'], block_data['y'], self.shape_definitions[name], block_data['orientation'])
            self.block_objects[id(block)] = block
        
        self.draw()
        messagebox.showinfo("Load Successful", f"Loaded {len(self.block_objects)} blocks.")

    def clear_fp(self, confirm=True):
        """Clears the entire floorplan."""
        if confirm and not messagebox.askyesno("Confirm Clear", "Clear the entire floorplan?"):
            return
        self.block_objects.clear()
        self.selected_blocks.clear()
        self.guideline_block_ids.clear()
        self.draw()

    # --- Advanced Actions (Bound to keys) ---
    def can_move(self, x_offset, y_offset):
        temp_grid_state = deepcopy(self.grid_state)
        selected_ids = {id(block) for block in self.selected_blocks}

        # Temporarily remove selected blocks from the grid for collision checking
        for x in range(self.grid_width):
            for y in range(self.grid_height):
                if temp_grid_state[x][y] in selected_ids:
                    temp_grid_state[x][y] = None

        for block in self.selected_blocks:
            new_x, new_y = block.data['x'] + x_offset, block.data['y'] + y_offset
            for dx, dy in block.block_shape:
                gx, gy = new_x + dx, new_y + dy
                if not (0 <= gx < self.grid_width and 0 <= gy < self.grid_height):
                    messagebox.showwarning("Move Warning", "Cannot move: out of boundaries!")
                    return False
                if temp_grid_state[gx][gy] is not None:
                    messagebox.showwarning("Move Warning", "Cannot move: position is occupied!")
                    return False
        return True

    def move(self, x_offset, y_offset):
        if not self.selected_blocks:
            messagebox.showwarning("Move Warning", "No block selected.")
            return False

        if not self.can_move(x_offset, y_offset):
            return False

        for block in self.selected_blocks:
            block.update_location(block.data['x'] + x_offset, block.data['y'] + y_offset)
        
        self.draw()
        return True

    def move_left(self, event=None): self.move(-1, 0)
    def move_right(self, event=None): self.move(1, 0)
    def move_up(self, event=None): self.move(0, -1)
    def move_down(self, event=None): self.move(0, 1)

    def duplicate_selected(self, event=None):
        if not self.selected_blocks:
            messagebox.showwarning("Duplicate Warning", "No block selected.")
            return

        direction = CustomDirectionDialog(self).result
        interval = simpledialog.askinteger("Input", "Enter the expected interval:", parent=self, minvalue=0)
        if direction is None or interval is None: return

        for block in list(self.selected_blocks.keys()):
            start_x, start_y = block.data['x'], block.data['y']
            block_width = block.urx_in_canvas - block.llx_in_canvas + 1
            block_height = block.ury_in_canvas - block.lly_in_canvas + 1

            if direction == "V":
                for i in range(1, self.grid_height):
                    new_y = start_y + i * (interval + block_height)
                    if new_y >= self.grid_height: break
                    if self._is_location_legal(start_x, new_y, block.data['cell_name']):
                        new_block = BlockObject(block.data['cell_name'], start_x, new_y, block.block_shape, 'R0')
                        self.block_objects[id(new_block)] = new_block
            elif direction == "H":
                for i in range(1, self.grid_width):
                    new_x = start_x + i * (interval + block_width)
                    if new_x >= self.grid_width: break
                    if self._is_location_legal(new_x, start_y, block.data['cell_name']):
                        new_block = BlockObject(block.data['cell_name'], new_x, start_y, block.block_shape, 'R0')
                        self.block_objects[id(new_block)] = new_block
        self.draw()

    def swap_selected(self, event=None):
        if len(self.selected_blocks) != 1 or not self.selected_shape:
            messagebox.showwarning("Swap Warning", "Select exactly one block to swap and a target shape from the list.")
            return
        
        block = next(iter(self.selected_blocks))
        
        if self.shape_definitions[block.data['cell_name']] == self.shape_definitions[self.selected_shape]:
            block.data['cell_name'] = self.selected_shape
        else:
            messagebox.showwarning("Swap Warning", f"Cannot swap blocks with different dimensions ('{self.selected_shape}').")
            return
        self.draw()

    def can_move_to(self, block, target_x, target_y):
        # Temporarily remove the block to check for collisions with others
        temp_grid_state = deepcopy(self.grid_state)
        for dx, dy in block.block_shape:
            gx, gy = block.data['x'] + dx, block.data['y'] + dy
            if 0 <= gx < self.grid_width and 0 <= gy < self.grid_height:
                if temp_grid_state[gx][gy] == id(block):
                    temp_grid_state[gx][gy] = None

        for dx, dy in block.block_shape:
            new_x, new_y = target_x + dx, target_y + dy
            if not (0 <= new_x < self.grid_width and 0 <= new_y < self.grid_height):
                messagebox.showwarning("Move Warning", "Cannot move to this location: out of boundaries!")
                return False
            if temp_grid_state[new_x][new_y] is not None:
                messagebox.showwarning("Move Warning", "Cannot move to this location: position is occupied!")
                return False
        return True

    def move_to_coord(self, event=None):
        if len(self.selected_blocks) != 1:
            messagebox.showwarning("Move Warning", "Please select exactly one block to move.")
            return

        coord_str = simpledialog.askstring("Move To", "Enter target coordinate (e.g., A42):")
        if not coord_str: return
        
        match = re.match(r"([A-Za-z]+)([0-9]+)", coord_str)
        if not match:
            messagebox.showwarning("Input Error", "Invalid coordinate format. Use Excel-style (e.g., A1, B22, AA5).")
            return

        col_str, row_str = match.groups()
        col = sum((ord(char) - ord('A') + 1) * (26 ** i) for i, char in enumerate(reversed(col_str.upper()))) - 1
        row = int(row_str) - 1
        
        block = next(iter(self.selected_blocks))
        if self.can_move_to(block, col, row):
            block.update_location(col, row)
            self.draw()

if __name__ == "__main__":
    args = read_args()
    project_name = args['project_name']
    config_file = os.path.join('input', project_name, f"{project_name}.csv")
    
    log.set_log_config("./pixel_drawing.log")
    log.logger.info(f"Reading project spec from {config_file}")
    
    designs = read_project_config(config_file)
    if not designs:
        log.logger.error("No designs found. Exiting.")
    else:
        for design in designs:
            app = BlockPlacement(
                project_name, 
                design['design_name'], 
                design['grid_width'], 
                design['grid_height']
            )
            app.mainloop()
