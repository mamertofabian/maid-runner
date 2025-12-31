"""Export functions for the Knowledge Graph.

This module provides functions to export a KnowledgeGraph to various formats.
Supports JSON, DOT (Graphviz), and GraphML export.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict

from maid_runner.graph.model import (
    ArtifactNode,
    Edge,
    FileNode,
    KnowledgeGraph,
    ManifestNode,
    ModuleNode,
    Node,
    NodeType,
)


def graph_to_dict(graph: KnowledgeGraph) -> Dict[str, Any]:
    """Convert a KnowledgeGraph to a dictionary representation.

    Args:
        graph: The KnowledgeGraph to convert.

    Returns:
        A dictionary with 'nodes' and 'edges' keys, containing lists of
        serialized node and edge data.
    """
    nodes_list = []
    for node in graph.nodes:
        node_dict = _node_to_dict(node)
        nodes_list.append(node_dict)

    edges_list = []
    for edge in graph.edges:
        edge_dict = _edge_to_dict(edge)
        edges_list.append(edge_dict)

    return {"nodes": nodes_list, "edges": edges_list}


def export_json(graph: KnowledgeGraph, output_path: Path) -> None:
    """Export a KnowledgeGraph to a JSON file.

    Converts the graph to a dictionary representation and writes it to the
    specified output path. Creates parent directories if they don't exist.

    Args:
        graph: The KnowledgeGraph to export.
        output_path: Path where the JSON file will be written.

    Returns:
        None
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    graph_dict = graph_to_dict(graph)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(graph_dict, f, indent=2)


def _node_to_dict(node: Node) -> Dict[str, Any]:
    """Convert a Node to a dictionary representation.

    Handles specialized node types (ManifestNode, FileNode, ArtifactNode,
    ModuleNode) by including their specific attributes.

    Args:
        node: The node to convert.

    Returns:
        A dictionary containing the node's data.
    """
    result: Dict[str, Any] = {
        "id": node.id,
        "type": node.node_type.value,
        "attributes": node.attributes,
    }

    if isinstance(node, ManifestNode):
        result["path"] = node.path
        result["goal"] = node.goal
        result["task_type"] = node.task_type
        result["version"] = node.version
    elif isinstance(node, FileNode):
        result["path"] = node.path
        result["status"] = node.status
    elif isinstance(node, ArtifactNode):
        result["name"] = node.name
        result["artifact_type"] = node.artifact_type
        result["signature"] = node.signature
        result["parent_class"] = node.parent_class
    elif isinstance(node, ModuleNode):
        result["name"] = node.name
        result["package"] = node.package

    return result


def _edge_to_dict(edge: Edge) -> Dict[str, Any]:
    """Convert an Edge to a dictionary representation.

    Args:
        edge: The edge to convert.

    Returns:
        A dictionary containing the edge's data.
    """
    return {
        "id": edge.id,
        "source": edge.source_id,
        "target": edge.target_id,
        "type": edge.edge_type.value,
        "attributes": edge.attributes,
    }


def graph_to_dot(graph: KnowledgeGraph) -> str:
    """Convert a KnowledgeGraph to DOT format for Graphviz visualization.

    Args:
        graph: The KnowledgeGraph to convert.

    Returns:
        A string containing the graph in DOT format.
    """
    lines = ["digraph G {"]

    # Add nodes
    for node in graph.nodes:
        node_str = _node_to_dot(node)
        lines.append(f"    {node_str}")

    # Add edges
    for edge in graph.edges:
        edge_str = _edge_to_dot_line(edge)
        lines.append(f"    {edge_str}")

    lines.append("}")
    return "\n".join(lines)


def export_dot(graph: KnowledgeGraph, output_path: Path) -> None:
    """Export a KnowledgeGraph to a DOT file.

    Converts the graph to DOT format and writes it to the specified output path.
    Creates parent directories if they don't exist.

    Args:
        graph: The KnowledgeGraph to export.
        output_path: Path where the DOT file will be written.

    Returns:
        None
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dot_content = graph_to_dot(graph)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(dot_content)


def _get_node_shape(node: Node) -> str:
    """Get the DOT shape for a node based on its type.

    Args:
        node: The node to get the shape for.

    Returns:
        A string representing the DOT shape.
    """
    shape_map = {
        NodeType.MANIFEST: "box",
        NodeType.FILE: "ellipse",
        NodeType.ARTIFACT: "diamond",
        NodeType.MODULE: "hexagon",
    }
    return shape_map.get(node.node_type, "ellipse")


def _get_node_label(node: Node) -> str:
    """Get the label for a node based on its type and attributes.

    Args:
        node: The node to get the label for.

    Returns:
        A string to use as the node label.
    """
    if isinstance(node, ManifestNode):
        # Include goal or path in the label
        if node.goal:
            return node.goal
        return node.path
    elif isinstance(node, FileNode):
        return node.path
    elif isinstance(node, ArtifactNode):
        return node.name
    elif isinstance(node, ModuleNode):
        return node.name
    else:
        return node.id


def _escape_dot_string(s: str) -> str:
    """Escape special characters in a string for DOT format.

    Args:
        s: The string to escape.

    Returns:
        The escaped string safe for DOT format.
    """
    # Escape backslashes first, then quotes
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _node_to_dot(node: Node) -> str:
    """Convert a Node to a DOT format node declaration.

    Args:
        node: The node to convert.

    Returns:
        A string representing the node in DOT format.
    """
    node_id = _escape_dot_string(node.id)
    label = _escape_dot_string(_get_node_label(node))
    shape = _get_node_shape(node)

    return f'"{node_id}" [label="{label}" shape={shape}];'


def _edge_to_dot_line(edge: Edge) -> str:
    """Convert an Edge to a DOT format edge declaration.

    Args:
        edge: The edge to convert.

    Returns:
        A string representing the edge in DOT format.
    """
    source_id = _escape_dot_string(edge.source_id)
    target_id = _escape_dot_string(edge.target_id)
    edge_label = edge.edge_type.value

    return f'"{source_id}" -> "{target_id}" [label="{edge_label}"];'


def graph_to_graphml(graph: KnowledgeGraph) -> str:
    """Convert a KnowledgeGraph to GraphML format.

    GraphML is an XML-based file format for graphs, designed for interoperability
    with graph analysis tools like Gephi, yEd, and NetworkX.

    Args:
        graph: The KnowledgeGraph to convert.

    Returns:
        A string containing the graph in GraphML format.
    """
    # Define namespace
    ns = "http://graphml.graphdrawing.org/xmlns"

    # Create root graphml element with namespace
    graphml = ET.Element("graphml", xmlns=ns)

    # Add key definitions for node and edge attributes
    node_type_key = ET.SubElement(graphml, "key")
    node_type_key.set("id", "node_type")
    node_type_key.set("for", "node")
    node_type_key.set("attr.name", "node_type")
    node_type_key.set("attr.type", "string")

    edge_type_key = ET.SubElement(graphml, "key")
    edge_type_key.set("id", "edge_type")
    edge_type_key.set("for", "edge")
    edge_type_key.set("attr.name", "edge_type")
    edge_type_key.set("attr.type", "string")

    # Create graph element
    graph_elem = ET.SubElement(graphml, "graph")
    graph_elem.set("id", "G")
    graph_elem.set("edgedefault", "directed")

    # Add nodes
    for node in graph.nodes:
        node_elem = ET.SubElement(graph_elem, "node")
        node_elem.set("id", node.id)

        # Add node_type data
        data_elem = ET.SubElement(node_elem, "data")
        data_elem.set("key", "node_type")
        data_elem.text = node.node_type.value

    # Add edges
    for i, edge in enumerate(graph.edges):
        edge_elem = ET.SubElement(graph_elem, "edge")
        edge_elem.set("id", f"e{i}")
        edge_elem.set("source", edge.source_id)
        edge_elem.set("target", edge.target_id)

        # Add edge_type data
        data_elem = ET.SubElement(edge_elem, "data")
        data_elem.set("key", "edge_type")
        data_elem.text = edge.edge_type.value

    # Convert to string with XML declaration
    xml_str = ET.tostring(graphml, encoding="unicode")

    # Add XML declaration
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'


def export_graphml(graph: KnowledgeGraph, output_path: Path) -> None:
    """Export a KnowledgeGraph to a GraphML file.

    Converts the graph to GraphML format and writes it to the specified output path.
    Creates parent directories if they don't exist.

    Args:
        graph: The KnowledgeGraph to export.
        output_path: Path where the GraphML file will be written.

    Returns:
        None
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    graphml_content = graph_to_graphml(graph)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(graphml_content)
