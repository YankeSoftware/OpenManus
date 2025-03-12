"""Utilities for chunking large documents into smaller pieces for LLM processing."""

import re
from typing import List, Optional, Tuple, Dict, Any

from app.config import config
from app.logger import logger

# Default token estimates (approximate)
AVG_CHARS_PER_TOKEN = 4  # Approximate for English text
DEFAULT_MAX_CHUNK_SIZE = config.document_processing.max_chunk_size
DEFAULT_CHUNK_OVERLAP = config.document_processing.chunk_overlap
TOKEN_SAFETY_MARGIN = config.document_processing.token_safety_margin


def estimate_tokens(text: str) -> int:
    """
    Estimate the number of tokens in a text string.
    This is a rough approximation - actual tokenization depends on the specific model.
    
    Args:
        text: Input text
        
    Returns:
        Estimated token count
    """
    if not text:
        return 0
        
    # Simple character-based token estimation
    return len(text) // AVG_CHARS_PER_TOKEN


def split_by_tokens(
    text: str,
    max_tokens: int = DEFAULT_MAX_CHUNK_SIZE,
    overlap_tokens: int = DEFAULT_CHUNK_OVERLAP,
    split_on: str = "\n\n"
) -> List[str]:
    """
    Split a document into chunks based on estimated token count,
    trying to preserve paragraph/section boundaries.
    
    Args:
        text: Input document text
        max_tokens: Maximum tokens per chunk
        overlap_tokens: Number of tokens to overlap between chunks
        split_on: Preferred text pattern to split on (e.g. "\n\n" for paragraphs)
        
    Returns:
        List of document chunks
    """
    if not text:
        return []
        
    # If text is short enough, return it as is
    if estimate_tokens(text) <= max_tokens:
        return [text]
        
    # Split the text into segments (paragraphs by default)
    segments = re.split(f"({split_on})", text)
    
    # Preserve the separators in the splits by joining them back with the segments
    preserved_segments = []
    for i in range(0, len(segments) - 1, 2):
        if i+1 < len(segments):
            preserved_segments.append(segments[i] + segments[i+1])
        else:
            preserved_segments.append(segments[i])
    
    # If there are no clean segment breaks, fall back to splitting by sentences
    if len(preserved_segments) <= 1:
        segments = re.split(r'(?<=[.!?])\s+', text)
        preserved_segments = segments
    
    chunks = []
    current_chunk = []
    current_token_count = 0
    last_segment_for_overlap = []
    overlap_token_count = 0
    
    for segment in preserved_segments:
        segment_tokens = estimate_tokens(segment)
        
        # If adding this segment exceeds our limit, save the current chunk and start a new one
        if current_token_count + segment_tokens > max_tokens and current_chunk:
            # Finish the current chunk
            chunks.append("".join(current_chunk))
            
            # Start a new chunk with the overlap from the previous chunk
            current_chunk = last_segment_for_overlap.copy()
            current_token_count = overlap_token_count
            
            # Reset the overlap tracking
            last_segment_for_overlap = []
            overlap_token_count = 0
        
        # Add the current segment to the chunk
        current_chunk.append(segment)
        current_token_count += segment_tokens
        
        # Update the overlap window (keep adding segments until we reach overlap_tokens)
        last_segment_for_overlap.append(segment)
        overlap_token_count += segment_tokens
        
        # Only keep enough segments for the desired overlap
        while overlap_token_count > overlap_tokens and len(last_segment_for_overlap) > 1:
            removed_segment = last_segment_for_overlap.pop(0)
            overlap_token_count -= estimate_tokens(removed_segment)
    
    # Add the final chunk if it has content
    if current_chunk:
        chunks.append("".join(current_chunk))
    
    logger.info(f"Split document into {len(chunks)} chunks (max {max_tokens} tokens per chunk)")
    return chunks


def process_document_in_chunks(
    document: str,
    process_function: callable,
    max_tokens: int = DEFAULT_MAX_CHUNK_SIZE,
    overlap_tokens: int = DEFAULT_CHUNK_OVERLAP,
    max_chunks_per_session: int = config.document_processing.max_chunks_per_session,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Process a large document in chunks using the provided function.
    
    Args:
        document: The document text to process
        process_function: Function that processes each chunk (must accept a text string as first arg)
        max_tokens: Maximum tokens per chunk
        overlap_tokens: Number of tokens to overlap between chunks
        max_chunks_per_session: Maximum number of chunks to process in one session
        **kwargs: Additional arguments to pass to the process_function
        
    Returns:
        List of results from processing each chunk
    """
    # Split the document into chunks
    chunks = split_by_tokens(
        document, 
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens
    )
    
    results = []
    
    # Process chunks in batches
    for i in range(0, len(chunks), max_chunks_per_session):
        batch = chunks[i:i+max_chunks_per_session]
        
        for j, chunk in enumerate(batch):
            chunk_number = i + j + 1
            context = {
                "chunk_number": chunk_number,
                "total_chunks": len(chunks),
                "is_first_chunk": chunk_number == 1,
                "is_last_chunk": chunk_number == len(chunks)
            }
            
            # Include chunk number information in the processing
            logger.info(f"Processing chunk {chunk_number}/{len(chunks)}")
            
            # Add context information to kwargs
            kwargs["chunk_context"] = context
            
            # Process this chunk
            result = process_function(chunk, **kwargs)
            results.append({
                "chunk_number": chunk_number,
                "total_chunks": len(chunks),
                "result": result
            })
    
    return results 