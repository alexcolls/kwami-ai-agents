import logging
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from zep_cloud.client import AsyncZep
from config import settings

router = APIRouter()
logger = logging.getLogger("kwami-api.memory")

async def get_zep_client():
    if not settings.zep_api_key:
        raise HTTPException(status_code=503, detail="Memory service not configured (ZEP_API_KEY missing)")
    return AsyncZep(api_key=settings.zep_api_key)

@router.get("/debug/{user_id}")
async def debug_user_memory(user_id: str, client: AsyncZep = Depends(get_zep_client)):
    """Debug endpoint to check what memory exists for a user."""
    result = {
        "user_id": user_id, 
        "facts": [], 
        "graph_edges": [],
        "graph_nodes": 0,
        "threads": [],
        "errors": []
    }
    
    # Try to get facts via graph.search (Zep v3 method)
    try:
        facts_response = await client.graph.search(
            user_id=user_id,
            query="user information",
            scope="edges",
            limit=20,
        )
        if facts_response and facts_response.edges:
            result["facts"] = [edge.fact for edge in facts_response.edges if hasattr(edge, 'fact') and edge.fact]
            result["graph_edges"] = [
                {"fact": edge.fact, "name": edge.name if hasattr(edge, 'name') else None}
                for edge in facts_response.edges if hasattr(edge, 'fact')
            ]
    except Exception as e:
        result["errors"].append(f"graph.search: {str(e)}")
    
    # Try graph nodes API
    try:
        nodes = await client.graph.node.get_by_user_id(user_id=user_id, limit=10)
        result["graph_nodes"] = len(nodes) if nodes else 0
        if nodes:
            result["node_names"] = [n.name for n in nodes if hasattr(n, 'name')]
    except Exception as e:
        result["errors"].append(f"graph.node: {str(e)}")
    
    # List ALL threads to see what exists
    try:
        threads_response = await client.thread.list_all(page_size=50)
        all_threads = []
        if threads_response:
            threads_list = threads_response.threads if hasattr(threads_response, 'threads') else threads_response
            for t in (threads_list or []):
                thread_id = t.thread_id if hasattr(t, 'thread_id') else (t.uuid if hasattr(t, 'uuid') else str(t))
                thread_user = t.user_id if hasattr(t, 'user_id') else None
                all_threads.append({
                    "thread_id": thread_id,
                    "user_id": thread_user,
                })
        result["all_threads"] = all_threads  # Show ALL threads for debugging
        
        # Now filter to this user and get context
        for t_info in all_threads:
            if t_info["user_id"] == user_id or (t_info["thread_id"] and user_id in str(t_info["thread_id"])):
                try:
                    ctx = await client.thread.get_context(thread_id=t_info["thread_id"])
                    if ctx and ctx.context:
                        t_info["context"] = ctx.context[:500] + "..." if len(ctx.context) > 500 else ctx.context
                except Exception as ctx_err:
                    t_info["context_error"] = str(ctx_err)[:100]
                result["threads"].append(t_info)
    except Exception as e:
        result["errors"].append(f"thread.list_all: {str(e)}")
    
    return result


@router.get("/{user_id}/facts")
async def get_user_facts(user_id: str, client: AsyncZep = Depends(get_zep_client)):
    """Get all facts stored for a user via graph search (Zep v3)."""
    try:
        # Zep v3 stores facts on graph edges - search for them
        facts_response = await client.graph.search(
            user_id=user_id,
            query="user information facts preferences",
            scope="edges",
            limit=50,
        )
        if facts_response and facts_response.edges:
            return [edge.fact for edge in facts_response.edges if hasattr(edge, 'fact') and edge.fact]
        return []
    except Exception as e:
        # Check for 404 (user not found)
        if "404" in str(e):
            return []
        logger.error(f"Failed to fetch facts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{user_id}/graph")
async def get_memory_graph(user_id: str, limit: int = 50, client: AsyncZep = Depends(get_zep_client)):
    """Get the knowledge graph representation of the user's memory from Zep."""
    logger.info(f"📊 Fetching memory graph for user: {user_id}")
    try:
        nodes = []
        edges = []
        node_map = {}  # Track nodes by name to avoid duplicates
        graph_edges_raw = []  # Store raw edges for relationship building
        
        # 1. Get edges via graph.search (for relationships)
        try:
            facts_response = await client.graph.search(
                user_id=user_id,
                query="*",  # Broader search
                scope="edges",
                limit=limit,
            )
            if facts_response and facts_response.edges:
                logger.info(f"📊 Got {len(facts_response.edges)} edges from graph.search")
                for edge in facts_response.edges:
                    edge_data = {
                        "fact": edge.fact if hasattr(edge, 'fact') else None,
                        "relation": edge.name if hasattr(edge, 'name') else "related_to",
                        "source_node": edge.source_node_uuid if hasattr(edge, 'source_node_uuid') else None,
                        "target_node": edge.target_node_uuid if hasattr(edge, 'target_node_uuid') else None,
                    }
                    graph_edges_raw.append(edge_data)
        except Exception as e:
            logger.warning(f"📊 graph.search edges failed: {e}")
        
        # 2. Get nodes (entities) from graph.node API
        entity_nodes = []
        try:
            nodes_response = await client.graph.node.get_by_user_id(user_id=user_id, limit=limit)
            if nodes_response:
                logger.info(f"📊 Got {len(nodes_response)} nodes from graph.node")
                for node in nodes_response:
                    node_name = node.name if hasattr(node, 'name') else "Unknown"
                    node_type = node.labels[0].lower() if hasattr(node, 'labels') and node.labels else "entity"
                    # Note: Zep uses uuid_ not uuid
                    node_uuid = node.uuid_ if hasattr(node, 'uuid_') else (node.uuid if hasattr(node, 'uuid') else None)
                    # created_at is already a string from Zep
                    created_at = node.created_at if hasattr(node, 'created_at') else None
                    entity_nodes.append({
                        "name": node_name,
                        "type": node_type,
                        "summary": node.summary if hasattr(node, 'summary') else None,
                        "uuid": node_uuid,
                        "created_at": created_at,
                        "labels": list(node.labels) if hasattr(node, 'labels') and node.labels else [],
                    })
        except Exception as e:
            logger.warning(f"📊 graph.node failed: {e}")
        
        # 3. Fallback: Try getting facts from a broader search if no nodes found
        if not entity_nodes:
            logger.info("📊 No nodes found, trying broader fact search...")
            try:
                # Try multiple search queries
                for query in ["user", "information", "facts", "preferences", "personal"]:
                    facts_response = await client.graph.search(
                        user_id=user_id,
                        query=query,
                        scope="edges",
                        limit=limit,
                    )
                    if facts_response and facts_response.edges:
                        logger.info(f"📊 Found {len(facts_response.edges)} edges with query '{query}'")
                        for edge in facts_response.edges:
                            if hasattr(edge, 'fact') and edge.fact:
                                fact_text = edge.fact
                                # Create a pseudo-node from the fact
                                if fact_text not in [e.get("name") for e in entity_nodes]:
                                    entity_nodes.append({
                                        "name": fact_text[:60] + "..." if len(fact_text) > 60 else fact_text,
                                        "type": "fact",
                                        "summary": fact_text,
                                        "uuid": None,
                                        "created_at": None,
                                        "labels": ["Fact"],
                                    })
                        if entity_nodes:
                            break  # Found some data, stop searching
            except Exception as e:
                logger.warning(f"📊 Fallback fact search failed: {e}")
        
        # 4. Build the visualization graph
        # Add central user node
        nodes.append({
            "id": "user",
            "label": "User",
            "type": "user",
            "val": 25
        })
        node_map["user"] = "user"
        
        # Map UUIDs to node IDs for edge building
        uuid_to_id = {}
        
        # Add entity nodes
        for i, entity in enumerate(entity_nodes):
            node_id = f"entity_{i}"
            node_map[entity["name"].lower()] = node_id
            if entity.get("uuid"):
                uuid_to_id[entity["uuid"]] = node_id
            
            # Infer better type from name/content
            node_type = entity["type"]
            name_lower = entity["name"].lower()
            if any(w in name_lower for w in ["music", "hip hop", "rock", "jazz", "likes", "loves", "enjoys"]):
                node_type = "preference"
            elif any(w in name_lower for w in ["years old", "age", "born"]):
                node_type = "attribute"
            elif any(w in name_lower for w in ["city", "country", "location", "lives", "from"]):
                node_type = "location"
            
            nodes.append({
                "id": node_id,
                "label": entity["name"],
                "type": node_type,
                "summary": entity["summary"],
                "uuid": entity["uuid"],
                "created_at": entity["created_at"],
                "labels": entity["labels"],
                "val": 15
            })
        
        # 5. Build edges from raw graph edges (actual relationships)
        edges_added = set()
        for raw_edge in graph_edges_raw:
            source_uuid = raw_edge.get("source_node")
            target_uuid = raw_edge.get("target_node")
            relation = raw_edge.get("relation", "related_to")
            
            source_id = uuid_to_id.get(source_uuid)
            target_id = uuid_to_id.get(target_uuid)
            
            if source_id and target_id and source_id != target_id:
                edge_key = f"{source_id}-{target_id}-{relation}"
                if edge_key not in edges_added:
                    edges.append({
                        "source": source_id,
                        "target": target_id,
                        "relation": relation
                    })
                    edges_added.add(edge_key)
        
        # 6. If no edges from graph, connect all nodes to user
        if not edges and len(nodes) > 1:
            logger.info("📊 No graph edges found, connecting nodes to user")
            for i, node in enumerate(nodes[1:], start=0):  # Skip user node
                edges.append({
                    "source": "user",
                    "target": node["id"],
                    "relation": "has"
                })
        
        logger.info(f"📊 Final graph: {len(nodes)} nodes, {len(edges)} edges")
        return {"nodes": nodes, "edges": edges}
        
    except Exception as e:
        logger.error(f"Failed to fetch memory graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


